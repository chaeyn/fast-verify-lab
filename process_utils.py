"""Start and stop private CLI process groups on supported operating systems."""
import asyncio
import os
import signal
import subprocess


def process_options():
    """Keep CLI descendants in a group that can be stopped on cancellation."""
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


async def stop_process_tree(process):
    """Stop a running CLI and its descendants, then reap the direct child.

    Windows does not have killpg. taskkill /T handles CLI launcher children.
    Prompts and credentials never enter the taskkill command.
    """
    if os.name != 'nt':
        # Descendants can retain our pipes after the direct child has exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.returncode is None:
        try:
            killer = await asyncio.create_subprocess_exec(
                'taskkill', '/PID', str(process.pid), '/T', '/F',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(killer.wait(), 5)
            except TimeoutError:
                killer.kill()
                await killer.wait()
        except OSError:
            pass
    # taskkill can fail if a process exits between lookup and termination.
    # Reap it in either case. Fall back to the direct child when needed.
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()
