"""Interactive terminal UI for Fast Verify Lab; uses the Python standard library."""
import argparse
import asyncio
import curses
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import sys
import threading
import time
import unicodedata

from lab import CodexProvider, MockProvider, OpenAIProvider, MODES, grade, run

ROOT = Path(__file__).resolve().parent
PROVIDERS = ('codex', 'mock', 'openai')


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
        self.cases = [json.loads(line) for line in Path(args.cases).read_text().splitlines() if line.strip()]
        if not self.cases:
            raise ValueError('No cases found')
        self.index, self.custom = 0, None
        self.provider, self.mode = args.provider, args.mode
        self.worker = None
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
            self.message = 'Use codex or openai for custom prompts. Mock supports sample cases only.'
            return
        self.events, self.result, self.saved = [], None, None
        self.scroll = 0
        try:
            config_path = self.args.config or ROOT / ('config.codex.json' if self.provider == 'codex' else 'config.example.json')
            config = json.loads(Path(config_path).read_text())
            provider = MockProvider() if self.provider == 'mock' else {'codex': CodexProvider, 'openai': OpenAIProvider}[self.provider](config)
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
                self.message = {'draft': 'Draft ready. Waiting for review.',
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
        folder = Path(self.args.output)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime('ui-%Y%m%dT%H%M%S%f') + '.json'
            path = folder / name
            payload = {'provider': self.provider, 'mode': self.mode, 'question': self.case['question'],
                       'custom_question': self.custom is not None, 'result': self.result}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            self.saved = str(path.resolve())
        except OSError:
            self.message += ' Could not save the result file.'

    def key(self, key):
        if self.editing:
            if key == '\x1b':
                self.editing = False
            elif key in ('\n', '\r', curses.KEY_ENTER):
                if self.buffer.strip():
                    self.custom = {'id': 'custom', 'question': self.buffer.strip()}
                    self.editing = False
                    self.clear_display()
                    if self.provider != 'mock':
                        self.start()
            elif key == '\x15':
                self.buffer = ''
            elif key in ('\x7f', '\b', curses.KEY_BACKSPACE):
                self.buffer = self.buffer[:-1]
            elif isinstance(key, str) and key.isprintable():
                self.buffer += key
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
        lines = []
        def section(label, text):
            lines.append((label, 1))
            lines.extend((line, 0) for line in wrap(text, columns))
            lines.append(('', 0))
        section('PROMPT' if self.editing else 'QUESTION  ' + self.case['id'],
                (self.buffer or 'Type your prompt here.') if self.editing else self.case['question'])
        draft = next((e for e in self.events if e['event'] == 'draft'), None)
        final = next((e for e in reversed(self.events) if e['event'] == 'final'), None)
        section('DRAFT', draft['answer'] if draft else 'No draft yet.')
        verified = any(e['event'] == 'verified' for e in self.events)
        if verified:
            section('REVIEW', 'Review complete · No changes needed')
        elif final:
            section('REVIEW  /  CORRECTION' if final['status'] == 'corrected' else 'REVIEW  /  RESULT', final['answer'])
        else:
            section('REVIEW', 'Reviewing...' if self.running else 'This answer has not been reviewed.' if draft else 'No run yet.')
        if final:
            section('STATUS', final['status'] + ('  |  ' + final['reason'] if final.get('reason') else ''))
        if self.result and self.result.get('calls'):
            result = self.result
            first = result.get('first_answer_ms')
            section('METRICS', f"First answer {first / 1000:.2f}s" if first is not None else 'No first answer')
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
    put(0, 'FAST VERIFY LAB', curses.A_BOLD | curses.color_pair(1))
    put(1, f"provider: {session.provider}   mode: {session.mode}   " + (f'running {elapsed:.1f}s' if session.running else 'ready'))
    put(2, '-' * (columns - 3), curses.A_DIM)
    lines = session.content(columns - 3)
    height = rows - 7
    session.scroll = min(session.scroll, max(0, len(lines) - height))
    for index, (text, accent) in enumerate(lines[session.scroll:session.scroll + height]):
        put(3 + index, text, curses.A_BOLD | curses.color_pair(1) if accent else 0)
    put(rows - 4, session.message, curses.color_pair(2))
    if session.editing:
        put(rows - 3, 'PROMPT  Enter: run  Esc: cancel  Ctrl+U: clear')
        edit_lines = wrap(session.buffer + '|', columns - 3)
        put(rows - 2, edit_lines[-1])
    else:
        put(rows - 3, 'Enter run | n new | e edit | Up/Down cases | p provider | m mode')
        put(rows - 2, 'PgUp/PgDn scroll | x cancel run | q quit', curses.A_DIM)
    screen.refresh()


def application(screen, session):
    curses.curs_set(0)
    screen.timeout(100)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
    try:
        while True:
            session.poll()
            draw(screen, session)
            try:
                key = screen.get_wch()
            except curses.error:
                continue
            if not session.key(key):
                break
    finally:
        if session.worker and session.worker.thread.is_alive():
            session.worker.cancel()
            session.worker.thread.join(timeout=2)
        session.poll()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=PROVIDERS, default='codex')
    parser.add_argument('--mode', choices=MODES, default='sequential')
    parser.add_argument('--config')
    parser.add_argument('--cases', default=str(ROOT / 'data/cases.jsonl'))
    parser.add_argument('--output', default=str(ROOT / 'results'))
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(2, 'TUI requires an interactive terminal. Run python3 tui.py in a terminal.\n')
    try:
        curses.wrapper(application, Session(args))
    except (OSError, ValueError, curses.error) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
