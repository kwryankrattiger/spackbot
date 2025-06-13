# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from gidgethub import sansio
from gidgethub import aiohttp as gh_aiohttp
from spackbot.routes import router
from spackbot.auth import authenticate_installation
from spackbot.helpers import get_logger

# take environment variables from .env file (if present)
load_dotenv()

logger = get_logger(__name__)

#: Location for authenticatd app to get a token for one of its installations
INSTALLATION_TOKEN_URL = "app/installations/{installation_id}/access_tokens"

#: get app parameters we expect in environment or .env
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
REQUESTER = os.environ.get("GITHUB_APP_REQUESTER")

routes = web.RouteTableDef()


@routes.post("/")
async def main(request):
    """Main entrypoint for all routes"""
    # read the GitHub webhook payload
    body = await request.read()

    # a representation of GitHub webhook event
    event = sansio.Event.from_http(request.headers, body, secret=WEBHOOK_SECRET)

    if event.data["repo"]["name"] not in cfg.CONFIG:
        # If the repo is not configured it is not allowed to send
        # events to this installation of spackbot
        logger.info(f"Rejected event {event}")
        return web.Response(status=405)

    logger.info(f"Received event {event}")

    # get an installation token to make a GitHubAPI for API calls
    installation_id = event.data["installation"]["id"]
    token = await authenticate_installation(installation_id)

    dispatch_kwargs = {
        "token": token,
    }

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, REQUESTER, oauth_token=token)

        # call the appropriate callback for the event
        await router.dispatch(event, gh, session=session, **dispatch_kwargs)

    # return a "Success"
    return web.Response(status=200)


if __name__ == "__main__":
    app = web.Application()
    app.add_routes(routes)
    port = os.environ.get("PORT") or None
    if port:
        port = int(port)

    web.run_app(app, port=port)
