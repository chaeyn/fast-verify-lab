"""Command-line interface for installed and source checkouts."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unicodedata

if __package__:
    from . import __version__
    from . import lab
    from .paths import cases_path, config_path, user_results_dir, configure_stdio
    from .providers import PROVIDERS, load_config
else:
    from __init__ import __version__
    import lab
    from paths import cases_path, config_path, user_results_dir, configure_stdio
    from providers import PROVIDERS, load_config


def safe_text(text):
    """Keep model output from sending control sequences to a terminal."""
    return ''.join(c for c in text if c in ('\n', '\t') or not unicodedata.category(c).startswith('C'))


class Printer:
    def __init__(self, json_output=False):
        self.json_output = json_output
        self.streamed = False

    def __call__(self, event):
        if self.json_output:
            print(json.dumps(event, ensure_ascii=False), flush=True)
            return
        kind = event['event']
        if kind == 'draft_delta':
            print(safe_text(event['delta']), end='', flush=True)
            self.streamed = True
        elif kind == 'draft':
            print('' if self.streamed else safe_text(event['answer']), flush=True)
            if event['status'] == 'verifying':
                print('Review in progress.', file=sys.stderr, flush=True)
        elif kind == 'verified':
            print('Review complete. No changes needed.', file=sys.stderr, flush=True)
        elif kind == 'final':
            if event['status'] != 'unreviewed':
                print('\nCorrection:' if event['status'] == 'corrected' else '\nUncertain answer:', flush=True)
            print(safe_text(event['answer']), flush=True)
            if event.get('reason'):
                print(safe_text(event['reason']), file=sys.stderr, flush=True)
        elif kind == 'error':
            print('Review failed. The draft is not verified.' if event['status'] == 'verification_failed'
                  else 'Request failed.', file=sys.stderr, flush=True)
            if event.get('error_message'):
                print(safe_text(event['error_message']), file=sys.stderr, flush=True)


def question_case(args):
    if args.provider == 'mock':
        if not args.case or args.question is not None or args.prompt_file:
            raise ValueError('Mock accepts a sample case only. Use --provider mock --case multiply, or fast-verify demo.')
        cases = [json.loads(line) for line in cases_path().read_text(encoding='utf-8').splitlines() if line.strip()]
        match = next((case for case in cases if case['id'] == args.case), None)
        if match is None:
            raise ValueError('Unknown case: ' + args.case)
        return match
    if args.case:
        raise ValueError('--case is only available with --provider mock')
    if args.question is not None and args.prompt_file:
        raise ValueError('Use one input source: QUESTION, --prompt-file, or standard input')
    if args.prompt_file:
        question = Path(args.prompt_file).expanduser().read_text(encoding='utf-8')
    elif args.question is not None:
        question = args.question
    elif not sys.stdin.isatty():
        question = sys.stdin.read()
    else:
        raise ValueError('Supply QUESTION, --prompt-file PATH, or pipe a question to standard input')
    if not question.strip():
        raise ValueError('The question is empty')
    return {'id': 'custom', 'question': question.strip()}


async def ask(args):
    case = question_case(args)
    config = load_config(args.provider, args.config)
    provider = lab.make_provider(args.provider, config)
    try:
        if hasattr(provider, 'prepare'):
            provider.prepare(args.mode)
        result = await lab.run(provider, args.mode, case, Printer(args.json))
        if not args.no_save:
            folder = Path(args.output).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            filename = datetime.now(timezone.utc).strftime('ask-%Y%m%dT%H%M%S%f') + '.json'
            path = folder / filename
            path.write_text(json.dumps({'provider': args.provider, 'mode': args.mode,
                'question': case['question'], 'result': result}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Saved: {path.resolve()}', file=sys.stderr)
        return int(result['status'] in ('failed', 'verification_failed'))
    finally:
        if hasattr(provider, 'close'):
            await asyncio.to_thread(provider.close)


def parser():
    result = argparse.ArgumentParser(description='Show a fast answer, then review it with a second model.')
    result.add_argument('--version', action='version', version=f'fast-verify {__version__}')
    sub = result.add_subparsers(dest='command', required=True)
    for command, help_text in [('tui', 'Open the terminal interface'), ('setup', 'Configure draft and review connections'),
                               ('doctor', 'Check local installation and login'), ('demo', 'Run one sample case'),
                               ('bench', 'Run the sample benchmark')]:
        sub.add_parser(command, help=help_text, add_help=False)
    prompt = sub.add_parser('ask', help='Ask one question or read it from standard input')
    prompt.add_argument('question', nargs='?', help='Question text (omit to read standard input)')
    prompt.add_argument('--prompt-file', help='Read a UTF-8 question file')
    prompt.add_argument('--provider', choices=PROVIDERS, default='configured')
    prompt.add_argument('--config', help='Path to a connection JSON file')
    prompt.add_argument('--mode', choices=lab.MODES, default='sequential')
    prompt.add_argument('--json', action='store_true', help='Write events as JSON Lines to standard output')
    prompt.add_argument('--no-save', action='store_true', help='Do not save a local question and result record')
    prompt.add_argument('--output', default=str(user_results_dir()), help='Directory for saved records')
    prompt.add_argument('--case', help='Mock sample case ID (no custom question)')
    return result


def main(argv=None):
    configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    cli_parser = parser()
    try:
        # Pass through command options so source commands keep the same flags.
        if argv and argv[0] == 'tui':
            if __package__:
                from .tui import main as tui_main
            else:
                from tui import main as tui_main
            return tui_main(argv[1:]) or 0
        if argv and argv[0] in ('setup', 'doctor'):
            if __package__:
                from .configure import main as configure_main
            else:
                from configure import main as configure_main
            return configure_main((['--doctor'] if argv[0] == 'doctor' else []) + argv[1:]) or 0
        if argv and argv[0] in ('demo', 'bench'):
            return lab.cli(argv) or 0
        args = cli_parser.parse_args(argv)
        return asyncio.run(ask(args))
    except KeyboardInterrupt:
        print('Cancelled.', file=sys.stderr)
        return 130
    except BrokenPipeError:
        # The downstream consumer closed its input. Provider cleanup ran in finally.
        return 1
    except (ValueError, KeyError, OSError) as exc:
        if isinstance(exc, FileNotFoundError) and getattr(exc, 'filename', None) == str(config_path()):
            cli_parser.exit(2, 'No connection config found. Run fast-verify setup.\n')
        cli_parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
