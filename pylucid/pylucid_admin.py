#!/usr/bin/python3

"""
    PyLucid Admin
    ~~~~~~~~~~~~~

    A interactive admin for PyLucid.

    :created: 08.02.2018 by Jens Diemer, www.jensdiemer.de
    :copyleft: 2018 by the PyLucid team, see AUTHORS for more details.
    :license: GNU General Public License v3 or later (GPLv3+), see LICENSE for more details.
"""

import cmd
import glob
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path

__version__ = "0.0.1"


if sys.version_info < (3, 5):
    print("\nERROR: Python 3.5 or greater is required!\n")
    sys.exit(101)


log = logging.getLogger(__name__)

SELF_FILENAME=os.path.basename(__file__)


def verbose_check_call(*args):
    """
    'verbose' version of subprocess.check_output()
    """
    print("Call: %r" % " ".join(args))
    try:
        subprocess.check_call(args, universal_newlines=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        print("\n***ERROR:")
        print(err.output)
        raise


def iter_subprocess_output(args):
    """
    A subprocess with tee ;)
    """
    print("Call: %s" % " ".join(args))

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"]="1" # If a python script called ;)

    proc=subprocess.Popen(args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, env=env, universal_newlines=True,
    )
    return iter(proc.stdout.readline,'')


def display_errors(func):
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as err:
            traceback.print_exc(file=sys.stderr)
            return "%s: %s" % (err.__class__.__name__, err)

    return wrapped


class Cmd2(cmd.Cmd):
    """
    Enhanced version of 'Cmd' class:
        - command alias
        - methods can be called directly from commandline: e.g.: ./foobar.py --help
        - Display
    """
    command_alias = { # used in self.precmd()
        "q": "quit",
        "--help": "help", "-h": "help", "-?": "help",
    }

    intro = (
        '\n{filename} shell v{version}\n'
        'Type help or ? to list commands.\n'
    ).format(
        filename=SELF_FILENAME,
        version=__version__
    )

    prompt = '%s> ' % SELF_FILENAME

    doc_leader = (
        "\nHint: All commands can be called directly from commandline.\n"
        "e.g.: $ ./{filename} pip_freeze\n"
    ).format(
        filename=SELF_FILENAME,
    )

    # Will be append to 'doc_leader' in self.do_help():
    complete_hint="\nUse <{key}> to command completion.\n"
    missing_complete="\n(Sorry, no command completion available.)\n" # if 'readline' not available

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # e.g.: $ ./pylucid.py upgrade_requirements -> run do_upgrade_requirements() on startup
        self.cmdqueue = sys.argv[1:]

    @display_errors
    def _complete_path(self, text, line, begidx, endidx):
        """
        complete a command argument with a existing path

        usage e.g.:
            class FooCmd(Cmd2):
                def complete_foobar(self, text, line, begidx, endidx):
                    return self._complete_path(text, line, begidx, endidx)

                def do_foobar(self, path): # 'path' is type string!
                    print("path:", path)
        """
        try:
            destination = line.split(" ", 1)[1]
        except IndexError:
            destination = "."

        if destination=="~":
            return [os.sep]

        destination = Path(destination).expanduser().resolve()

        if not destination.is_dir():
            destination = destination.parent.resolve()

        if destination.is_dir():
            complete_list = [x.stem + os.sep for x in destination.iterdir() if x.is_dir()]
            if text:
                if text in complete_list:
                    return [text + os.sep]

                complete_list = [x for x in complete_list if x.startswith(text)]
        else:
            complete_list = []

        return complete_list

    _complete_hint_added=False
    def do_help(self, arg):
        if not self._complete_hint_added:
            try:
                import readline
            except ImportError:
                self.doc_leader += self.missing_complete
            else:
                self.doc_leader += self.complete_hint.format(key=self.completekey)
            self._complete_hint_added=True

        return super().do_help(arg)

    def do_quit(self, arg):
        "Exit this interactiv shell"
        print("\n\nbye")
        return True

    def precmd(self, line):
        try:
            return self.command_alias[line]
        except KeyError:
            return line

    def postcmd(self, stop, line):
        # stop if we are called with commandline arguments
        if len(sys.argv)>1:
            stop = True
        return stop




class PyLucidShell(Cmd2):

    #_________________________________________________________________________
    # Normal user commands:

    def _resolve_path(self, path):
        return Path(path).expanduser().resolve()

    def complete_boot(self, text, line, begidx, endidx):
        return self._complete_path(text, line, begidx, endidx)

    def do_boot(self, destination):
        """
        usage:
            > boot [path]

        Create a PyLucid virtualenv in the given [path].
        The destination path must not exist yet!
        """
        destination = Path(destination).expanduser().resolve()
        if destination.exists():
            self.stdout.write("\nERROR: Path '%s' already exists!\n" % destination)
            return

        print("TODO: boot install to: '%s'" % destination)

    #_________________________________________________________________________
    # Developer commands:

    def do_upgrade_requirements(self, arg):
        """
        Convert via 'pip-compile' *.in requirements files to *.txt
        Append 'piprot' informations to *.txt requirements.

        Direct start with:
            $ ./pylucid.py upgrade_requirements
        """
        for requirement_in in glob.glob(os.path.join("requirements", "*.in")):
            if "basic_" in requirement_in:
                continue
            requirement_out = requirement_in.replace(".in", ".txt")

            self.stdout.write("_"*79 + "\n")
            verbose_check_call("pip-compile", "--verbose", "--upgrade", "-o", requirement_out, requirement_in)

            self.stdout.write("_"*79 + "\n")
            args = ["piprot", "--outdated", requirement_out]
            output = [
                "\n#\n# list of out of date packages made with piprot:\n#\n"
            ]
            for line in iter_subprocess_output(args):
                self.stdout.write(line)
                self.stdout.flush()
                output.append("# %s" % line)

            self.stdout.write("\nUpdate file %r\n" % requirement_out)
            with open(requirement_out, "a") as f:
                f.writelines(output)

    def _install(self, requirements_filename):
        verbose_check_call("pip3", "install", "--upgrade", "pip")
        requirement = os.path.join("requirements", requirements_filename)
        verbose_check_call("pip3", "install", "-r", requirement)

    def do_install_normal(self, arg):
        """
        pip install -r normal_installation.txt

        The "normal" way for all PyLucid users:
        Use PyPi packages and read-only sources from github.
        """
        self._install("normal_installation.txt")

    def do_install_developer(self, arg):
        """
        pip install -r developer_installation.txt

        **only usable for developer with github write access**
        """
        self._install("developer_installation.txt")

    def do_install_ci(self, arg):
        """
        pip install -r ci_installation.txt

        **only for Travis CI**
        """
        self._install("ci_installation.txt")

    def do_pip_freeze(self, arg):
        "run 'pip freeze': FOO"
        verbose_check_call("pip3", "freeze")


def main():
    PyLucidShell().cmdloop()


if __name__ == '__main__':
    main()