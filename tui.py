"""Interactive terminal UI for Fast Verify Lab; uses the Python standard library."""
import argparse
import asyncio
try:
    import curses
except ImportError:
    curses = None
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import sys
import threading
import time
import unicodedata

if __package__:
    from .lab import MODES, grade, make_provider, run
    from .providers import PROVIDERS, load_config
    from .paths import ROOT, cases_path, config_path, user_results_dir
    from .configure import wizard
else:
    from lab import MODES, grade, make_provider, run
    from providers import PROVIDERS, load_config
    from paths import ROOT, cases_path, config_path, user_results_dir
    from configure import wizard

BANNER = (
    r" ____    _    ____ _____  __     _______ ____  ___ _____ __   __",
    r"|  __|  / \  / ___|_   _| \ \   / / ____|  _ \|_ _|  ___|\ \ / /",
    r"| |_   / _ \ \___ \ | |    \ \ / /|  _| | |_) || || |_    \ V / ",
    r"|  _| / ___ \ ___) || |     \ V / | |___|  _ < | ||  _|    | |  ",
    r"|_|  /_/   \_\____/ |_|      \_/  |_____|_| \_\___|_|      |_|  ",
)


def width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)


def wrap(text, columns):
    """Wrap by terminal cells; remove control characters from model-provided text."""
    lines = []
    for paragraph in str(text).split('\n'):
        current, used = '', 0
        for c in paragraph:
            if unicodedata.category(c).startswith('C'):
                c = ' '
            size = width(c)
            if used + size > columns and current:
                lines.append(current)
                current, used = '', 0
            current += c
            used += size
        lines.append(current)
    return lines


class Worker:
    def __init__(self, provider, mode, case):
        self.events = queue.Queue()
        self.provider, self.mode, self.case = provider, mode, case
        self.loop = self.task = None
        self.cancel_requested = threading.Event()
        self.thread = threading.Thread(target=self._work, daemon=True)

    def start(self):
        self.thread.start()

    def cancel(self):
        self.cancel_requested.set()
        if self.loop and self.task and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass

    def _work(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.task = self.loop.create_task(run(self.provider, self.mode, self.case,
            lambda event: self.events.put(('event', event))))
        if self.cancel_requested.is_set():
            self.task.cancel()
        try:
            result = self.loop.run_until_complete(self.task)
            self.events.put(('result', result))
        except asyncio.CancelledError:
            self.events.put(('cancelled', None))
        except Exception as exc:
            self.events.put(('failure', type(exc).__name__))
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()


class Session:
    def __init__(self, args):
        self.args = args
        self.cases = [json.loads(line) for line in Path(args.cases).read_text(encoding='utf-8').splitlines() if line.strip()]
        if not self.cases:
            raise ValueError('No cases found')
        self.index, self.custom = 0, None
        self.provider, self.mode = args.provider, args.mode
        self.help = False
        self.connection_labels = {}
        self.worker = None
        self.providers = {}
        self.running = False
        self.events = []
        self.result = None
        self.message = 'Press Enter to run, or e to edit the prompt.'
        self.saved = None
        self.started = 0
        self.scroll = 0
        self.editing, self.buffer = self.provider != 'mock', ''
        if self.editing:
            self.message = 'Type your prompt and press Enter to run.'

    @property
    def case(self):
        return self.custom or self.cases[self.index]

    def start(self):
        if self.running:
            return
        if self.provider == 'mock' and self.custom:
            self.message = 'Choose a live connection for custom prompts. Mock supports sample cases only.'
            return
        self.events, self.result, self.saved = [], None, None
        self.scroll = 0
        try:
            config = load_config(self.provider, self.args.config)
            cache_key = (self.provider, json.dumps(config, sort_keys=True))
            if cache_key not in self.providers:
                self.providers[cache_key] = make_provider(self.provider, config)
            provider = self.providers[cache_key]
            if hasattr(provider, 'prepare'):
                provider.prepare(self.mode)
        except (ValueError, OSError, KeyError) as exc:
            self.message = str(exc)
            return
        self.worker = Worker(provider, self.mode, dict(self.case))
        self.running, self.started = True, time.perf_counter()
        self.message = 'Running draft generation and review.'
        self.worker.start()

    def poll(self):
        if not self.worker:
            return
        while True:
            try:
                kind, item = self.worker.events.get_nowait()
            except queue.Empty:
                return
            if kind == 'event':
                self.events.append(item)
                self.message = {'draft_delta': 'Receiving the first answer...', 'draft': 'Draft ready. Waiting for review.',
                                'verified': 'Review complete. No changes needed.',
                                'final': 'Run complete.', 'error': 'Run failed. The draft has not passed review.'}.get(item['event'], '')
            else:
                self.running = False
                if kind == 'result':
                    self.result = item
                    if 'expected' in self.case:
                        item['grade'] = grade(item, self.case['expected'])
                    self.message = 'Run complete: ' + item['status']
                elif kind == 'cancelled':
                    self.result = {'status': 'cancelled', 'events': self.events, 'answer': None}
                    self.message = 'Cancelled. The draft has not passed review.'
                else:
                    self.result = {'status': 'failed', 'events': self.events, 'error_type': item}
                    self.message = 'Run failed: ' + item
                self.save()

    def save(self):
        if getattr(self.args, 'no_save', False):
            return
        folder = Path(self.args.output)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime('ui-%Y%m%dT%H%M%S%f') + '.json'
            path = folder / name
            payload = {'provider': self.provider, 'mode': self.mode, 'question': self.case['question'],
                       'custom_question': self.custom is not None, 'result': self.result}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            self.saved = str(path.resolve())
        except OSError:
            self.message += ' Could not save the result file.'

    def key(self, key):
        if key == curses.KEY_F1:
            self.help = not self.help
            return True
        if self.help:
            if key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                self.scroll = max(0, self.scroll + (10 if key == curses.KEY_NPAGE else -10))
                return True
            self.help = False
            self.scroll = 0
            return key != 'q'
        if self.editing:
            if key == '\x1b':
                self.editing = False
            elif key in ('\n', '\r', '\x04', curses.KEY_ENTER):
                if self.buffer.strip():
                    self.custom = {'id': 'custom', 'question': self.buffer.strip()}
                    self.editing = False
                    self.clear_display()
                    if self.provider != 'mock':
                        self.start()
            elif key == '\x0f':
                self.buffer += '\n'
            elif key == '\x17':
                self.buffer = self.buffer.rstrip()
                self.buffer = self.buffer[:max(self.buffer.rfind(' '), self.buffer.rfind('\n')) + 1]
            elif key == '\x15':
                self.buffer = ''
            elif key in ('\x7f', '\b', curses.KEY_BACKSPACE):
                self.buffer = self.buffer[:-1]
            elif isinstance(key, str) and key.isprintable():
                self.buffer += key
            return True
        if key == '?':
            self.help = True
            return True
        if key == 'q':
            if self.running:
                self.worker.cancel()
            return False
        if key == 'x' and self.running:
            self.worker.cancel()
            self.message = 'Cancelling...'
        if key == curses.KEY_NPAGE:
            self.scroll += 10
        elif key == curses.KEY_PPAGE:
            self.scroll = max(0, self.scroll - 10)
        if self.running:
            return True
        if key == 's':
            return 'setup'
        if key in ('\n', '\r', curses.KEY_ENTER):
            self.start()
        elif key == 'p':
            self.provider = PROVIDERS[(PROVIDERS.index(self.provider) + 1) % len(PROVIDERS)]
            self.clear_display()
        elif key == 'm':
            self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
            self.clear_display()
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            self.index = (self.index + (-1 if key == curses.KEY_UP else 1)) % len(self.cases)
            self.custom = None
            self.clear_display()
        elif key == 'n':
            self.clear_display()
            self.editing, self.buffer = True, ''
            self.message = 'Type a new prompt and press Enter to run.'
        elif key == 'e':
            self.editing, self.buffer = True, self.case['question']
        elif key == 'r':
            self.custom = None
            self.clear_display()
        return True

    def clear_display(self):
        self.events, self.result, self.saved, self.worker = [], None, None, None
        self.scroll = 0
        self.message = 'Press Enter to run, or e to edit the prompt.'

    def content(self, columns):
        if self.help:
            return [(part, 0) for line in (
                'HELP · FAST VERIFY LAB', '',
                'Enter: run prompt or selected sample', 'n: new prompt   e: edit   Esc: leave editor',
                'Ctrl+O: add newline   Ctrl+D: run multiline prompt',
                'Ctrl+U: clear prompt   Ctrl+W: delete last word',
                's: connection setup   p: cycle provider   m: mode   r: samples',
                'PgUp/PgDn: scroll   x: cancel run   q: quit',
                'F1: help from any screen   ?: help outside editor', '',
                'sequential: draft -> one review (recommended)',
                'fast / strong: one model, no review',
                'parallel: independent answer plus review (3 calls)', '',
                'accepted: reviewer kept the draft; answer shown once',
                'corrected: reviewer changed it; correction shown below',
                'uncertain: reviewer could not resolve the answer',
                'failed review: draft stays unverified', '',
                'Configure both connections: fast-verify setup',
                'Check installation and login: fast-verify doctor',
                'Results include prompts and answers. Use --no-save to disable.',
                'See GUIDE.md for setup, billing and troubleshooting.', '',
                'PgUp/PgDn to scroll; any other key closes help.') for part in wrap(line, columns)]
        lines = []
        def section(label, text):
            lines.append((label, 1))
            lines.extend((line, 0) for line in wrap(text, columns))
            lines.append(('', 0))
        section('PROMPT' if self.editing else 'QUESTION  ' + self.case['id'],
                (self.buffer or 'Type your prompt here.') if self.editing else self.case['question'])
        draft = next((e for e in self.events if e['event'] == 'draft'), None)
        final = next((e for e in reversed(self.events) if e['event'] == 'final'), None)
        partial = ''.join(e['delta'] for e in self.events if e['event'] == 'draft_delta')
        section('DRAFT · generating' if self.running and not draft else 'DRAFT', draft['answer'] if draft else partial or 'No draft yet.')
        verified = any(e['event'] == 'verified' for e in self.events)
        if verified:
            section('REVIEW', 'Review complete · No changes needed')
        elif final:
            section('REVIEW  /  CORRECTION' if final['status'] == 'corrected' else 'REVIEW  /  RESULT', final['answer'])
        else:
            section('REVIEW', 'Reviewing...' if self.running else 'This answer has not been reviewed.' if draft else 'No run yet.')
        if final:
            section('STATUS', final['status'] + ('  |  ' + final['reason'] if final.get('reason') else ''))
        if self.result and self.result.get('status') in ('failed', 'verification_failed'):
            error = next((e for e in reversed(self.events) if e['event'] == 'error'), {})
            if error.get('error_message'):
                section('CONNECTION ERROR', error['error_message'])
            section('RECOVERY', 'Check login and model access with fast-verify doctor.\nAPI: check your key, base URL and model IDs in config.\nEdit the question with e, or press Enter to retry.')
        if self.result and self.result.get('calls'):
            result = self.result
            first = result.get('first_answer_ms')
            section('METRICS', f"First answer {first / 1000:.2f}s" if first is not None else 'No first answer')
            if result.get('first_token_ms') is not None:
                lines.extend((line, 0) for line in wrap(f"First token {result['first_token_ms']/1000:.2f}s", columns))
            lines.extend((line, 0) for line in wrap(f"Completed {result['final_ms']/1000:.2f}s  |  Calls {len(result['calls'])}", columns))
            for call in result['calls']:
                usage = call.get('usage') or {}
                lines.extend((line, 0) for line in wrap(f"{call['stage']}: {call.get('model_label') or call.get('requested_model') or call.get('model') or '-'} ({call.get('requested_service_tier') or 'unspecified'})  input {usage.get('input_tokens', '-')} / output {usage.get('output_tokens', '-')}", columns))
        if self.saved:
            section('SAVED', self.saved)
        return lines


def draw(screen, session):
    screen.erase()
    rows, columns = screen.getmaxyx()
    def put(y, text, attr=0):
        if 0 <= y < rows:
            try:
                screen.addstr(y, 1 if columns > 2 else 0, wrap(text, max(1, columns - 3))[0], attr)
            except curses.error:
                pass
    if rows < 12 or columns < 40:
        put(0, 'Resize terminal to at least 40 x 12.')
        put(2, 'q: quit')
        screen.refresh()
        return
    elapsed = time.perf_counter() - session.started if session.running else 0
    large_banner = rows >= 26 and columns >= max(map(len, BANNER)) + 3
    header_rows = 0
    if large_banner:
        for row, line in enumerate(BANNER):
            put(row, line, curses.A_BOLD | curses.color_pair(3))
        header_rows = len(BANNER)
    put(header_rows, ' :: FAST VERIFY LAB ::  draft -> review' if large_banner else 'FAST VERIFY LAB',
        curses.A_BOLD | curses.color_pair(1))
    put(header_rows + 1, f"provider: {session.provider}   mode: {session.mode}   " + (f'running {elapsed:.1f}s' if session.running else 'ready'))
    try:
        if session.provider not in session.connection_labels:
            config = load_config(session.provider, session.args.config)
            session.connection_labels[session.provider] = config
        config = session.connection_labels[session.provider]
        roles = [f"{config[r].get('provider', session.provider)}/{config[r]['model']}" for r in ('fast', 'strong')]
        connection = ' -> '.join(roles)
    except (OSError, ValueError, KeyError):
        connection = 'Run fast-verify setup to configure connections'
    put(header_rows + 2, connection, curses.A_DIM)
    content_top = header_rows + 3
    lines = session.content(columns - 3)
    height = rows - content_top - 4
    session.scroll = min(session.scroll, max(0, len(lines) - height))
    for index, (text, accent) in enumerate(lines[session.scroll:session.scroll + height]):
        put(content_top + index, text, curses.A_BOLD | curses.color_pair(1) if accent else 0)
    put(rows - 4, session.message, curses.color_pair(2))
    if session.editing:
        put(rows - 3, 'Enter run | Ctrl+O newline | Ctrl+D run | Esc back | F1 help')
        edit_lines = wrap(session.buffer + '|', columns - 3)
        put(rows - 2, edit_lines[-1])
    else:
        put(rows - 3, 'Enter run | n new | e edit | s setup | p provider | m mode')
        put(rows - 2, 'PgUp/PgDn scroll | x cancel | q quit | F1 / ? help', curses.A_DIM)
    screen.refresh()


def application(screen, session):
    curses.curs_set(0)
    screen.timeout(100)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
    try:
        while True:
            session.poll()
            draw(screen, session)
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            rows, columns = screen.getmaxyx()
            if (rows < 12 or columns < 40) and key == 'q':
                break
            action = session.key(key)
            if action == 'setup':
                return 'setup'
            if not action:
                break
    finally:
        if session.worker and session.worker.thread.is_alive():
            session.worker.cancel()
            session.worker.thread.join(timeout=2)
        session.poll()
        for provider in session.providers.values():
            if hasattr(provider, 'close'):
                provider.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=PROVIDERS, default=None)
    parser.add_argument('--mode', choices=MODES, default='sequential')
    parser.add_argument('--config')
    parser.add_argument('--setup', action='store_true', help='Configure draft and review connections')
    parser.add_argument('--no-save', action='store_true', help='Do not save questions or answers locally')
    parser.add_argument('--cases', default=str(cases_path()))
    parser.add_argument('--output', default=str(user_results_dir()))
    args = parser.parse_args(argv)
    if curses is None:
        parser.exit(2, 'TUI support is missing. On Windows, run python -m pip install windows-curses. On Unix, use Python with curses. You can use fast-verify ask without curses.\n')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(2, 'TUI requires an interactive terminal. Run fast-verify tui in a terminal.\n')
    try:
        if args.setup or (args.provider is None and not args.config and not config_path().exists()):
            args.config = str(wizard(args.config))
        if args.provider is None:
            config = load_config('configured', args.config)
            if 'provider' not in config['fast']:
                raise ValueError('This config needs --provider (for example, --provider codex), or role-specific provider fields. Run fast-verify setup.')
            args.provider = 'configured'
        while curses.wrapper(application, Session(args)) == 'setup':
            args.config = str(wizard(args.config))
            args.provider = 'configured'
    except (EOFError, KeyboardInterrupt):
        parser.exit(130, 'Setup cancelled.\n')
    except (OSError, ValueError, KeyError, curses.error) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
