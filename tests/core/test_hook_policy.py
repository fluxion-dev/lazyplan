"""Which shell commands the commit gate treats as a git commit."""

import unittest

from lazyplan.core.policies.hooks import is_git_commit

COMMITS = (
    "git commit -m x",
    "git commit",
    "git commit --amend --no-edit",
    "git -C repo commit -m x",
    "git -c user.name=x commit -m x",
    "git --no-pager commit -m x",
    "git --git-dir .git --work-tree . commit -m x",
    "cd repo && git commit -m x",
    "git add . && git commit -m 'a && b'",
    "git add .; git commit -m x",
    "git status\ngit commit -m x",
    "(cd repo && git commit -m x)",
    "FOO=1 GIT_AUTHOR_NAME=x git commit -m x",
    "env GIT_EDITOR=true git commit",
    "if git commit -m x; then echo ok; fi",
    "/usr/bin/git commit -m x",
    "GIT.EXE commit -m x",
    "& 'C:\\Program Files\\Git\\cmd\\git.exe' commit -m x",
    "git add .; if ($?) { git commit -m 'x' }",
    "git commit -m \"$(cat <<'EOF'\nIt's done\nEOF\n)\"",
    "git commit -F- <<'EOF'\nIt's done\nEOF",
)

NOT_COMMITS = (
    "",
    "git status",
    "git log --grep 'git commit'",
    "grep -rn 'git commit' src",
    'echo "git commit"',
    "echo git commit",
    "lpui hook pre-tool --command 'git commit -m x'",
    "git commit-tree HEAD^{tree}",
    "git -C commit status",
    "gitk commit",
    "git show HEAD:commit.txt",
    "rg -n git src | grep commit",
)


class IsGitCommitCase(unittest.TestCase):
    def test_commands_that_run_a_commit(self):
        for command in COMMITS:
            with self.subTest(command=command):
                self.assertTrue(is_git_commit(command))

    def test_commands_that_only_mention_a_commit(self):
        for command in NOT_COMMITS:
            with self.subTest(command=command):
                self.assertFalse(is_git_commit(command))

    def test_an_unparsable_line_falls_back_to_the_command_start(self):
        self.assertTrue(is_git_commit("git commit -m 'unterminated"))
        self.assertFalse(is_git_commit("echo 'unterminated git commit"))


if __name__ == "__main__":
    unittest.main()
