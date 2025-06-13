import subprocess
from sh.contrib import git

import spackbot.comments as comments
import spackbot.config as cfg
import helpers

logger = helpers.get_logger(__name__)

allow_edits_url = (
    "https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/"
    "allowing-changes-to-a-pull-request-branch-created-from-a-fork"
    "#enabling-repository-maintainer-permissions-on-existing-pull-requests"
)

def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "nothing to commit" in output

async def fix_style(git_url: str, branch: str, user: str, email: str, files: List[str], style: cfg.Style):
    with helpers.temp_dir() as cwd:
        # Clone the repo
        git.clone(git_url, "fix-style")
        os.chdir("fix-style")

        # Confgire the user
        git.config("user.name", user)
        git.config("user.email", email)

        git.fetch("origin", f"{branch}:fix_style")
        git.checkout("fix_style")

        style_output = ""
        for command in style.tools:
            output = ""
            error = ""
            if style.strategy == Style.Strategy.BATCH:
                logger.debug("[command]")
                logger.debug(f"{command}")
                res = subprocess.run(command)
                output = res.stdout
                error = res.stderr
            elif style.strategy == Style.Strategy.FILE:
                for file in files:
                    cmd = command.format(file=file)
                    logger.debug("[command]")
                    logger.debug(f"{cmd}")
                    res = subprocess.run(cmd)
                    output += res.stdout
                    error += res.stderr

            logger.debug("[output]")
            logger.debug(output)
            logger.debug("[error]")
            logger.debug(error)

            style_output += output

        message = comments.get_style_message(style_output)

        # Only re-add listed files
        for file in files:
            git.add(file)

        commit_output = git.commit(
            "-m",
            f"[{helpers.botname}] updating style on behalf of @{user}"
        )

        if is_up_to_date(commit_output):
            logger.info("Unable to make any further changes")
            message += "\nI wasn't able to make any further changes, but please see the message above for remaining issues you can fix locally!"
            return message

        try:
            git.push(
                "origin",
                f"fix_style:{branch}",
                _ok_code=[0]
            )
            message += "\n\nI've updated the branch with style fixes."
        except ErrorReturnCode as inst:
            logger.error(f"Unable to push to branch {git_url}:{branch}")
                message += (
                    f"\n\nIt looks like I'm not able to push to your branch. 😭️"
                    f" Did you check [Allow edits from maintainers]({allow_edits_url})"
                    f" when you opened the PR?"
                )

        return message
