import pytest

from sh.contrib import git

def test_style_is_up_to_date(mock_git_repo):
    # Unmodified repo is up-to-date
    out = git.commit("-m", "some commit message")
    assert style.is_up_to_date(out)

    # Modify file in repo
    with open("a.txt", "a") as fd:
        fd.write("\nmodified")
    git.add("a.txt")

    # Modified repo is not up-to-date
    out = git.commit("-m", "modified a.txt")
    assert not style.is_up_to_date(out)


def test_fix_style_async(mock_git_repo):

    style.fix_style(
        mock_git_repo,
        "main",
        "mock",
        "noreply@mock.io",
        ["a.txt"],
        mock_config.style
    )
