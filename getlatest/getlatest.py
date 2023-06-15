#!/usr/bin/env python3

"""
This script downloads the latest version of binaries from Github and updates them.
Carrol Cox <carrol@proton.me>
"""

import os
import argparse
from typing import Tuple
import subprocess
import urllib.request
import json
import yaml
from aria2p import API
import re
import semver
import signal
import logging
from contextlib import contextmanager


@contextmanager
def timeout(seconds: int):
    def signal_handler(signum, frame):
        raise TimeoutError("Timed out!")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class GithubAPI:
    def __init__(
        self, owner: str, repo: str, regex: str, token: str, logger: logging.Logger
    ):
        self.owner = owner
        self.regex = regex
        self.repo = repo
        self.token = token
        self.logger = logger

    def github_request(self, url: str = None) -> dict:
        """Get JSON from Github API."""
        try:
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"token {self.token}")

            with urllib.request.urlopen(req) as response:
                return json.loads(response.read())

        except urllib.error.HTTPError as _err:
            logger.error("Github API HTTP Error: %s", _err)
            raise

        except urllib.error.URLError as _err:
            logger.error("Github API URL Error: %s", _err)
            raise

        except Exception as _err:
            logger.error("Github API Unknown Error: %s", _err)
            raise

    def get_response_from_github(self, param: str) -> str:
        """Retrieves the specified information from the latest release or first release in the Github repository."""
        # get latest release
        github_response = self.github_request(
            f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        )
        if not github_response:
            # retry, get first from releases
            github_response = self.github_request(
                f"https://api.github.com/repos/{self.owner}/{self.repo}/releases"
            )[0]

        if param == "version":
            return github_response["name"]
        if param == "asset":
            for asset in github_response["assets"]:
                if re.search(self.regex, asset["name"]):
                    return asset["browser_download_url"]
        return None


class GithubUpdater:
    def __init__(
        self,
        gh_token: str,
        tmp_dir: str,
        logger: logging.Logger,
        bin_dir: str = f"{os.environ['HOME']}/.local/bin",
        bin_name: str = None,
        bin_version: str = None,
        bin_version_arg: str = "--version",
        pkg_owner: str = None,
        pkg_regex: str = "linux_amd64",
        pkg_repo: str = None,
        pkg_type: str = None,
        pkg_url: str = None,
        pkg_version: str = None,
    ):
        self.gh_token = gh_token
        self.tmp_dir = tmp_dir
        self.logger = logger
        self.bin_dir = bin_dir
        self.bin_name = bin_name or pkg_repo
        self.bin_version = bin_version
        self.bin_version_arg = bin_version_arg
        self.pkg_owner = pkg_owner
        self.pkg_regex = pkg_regex
        self.pkg_repo = pkg_repo
        self.pkg_type = pkg_type
        self.pkg_url = pkg_url
        self.pkg_version = pkg_version

    def process_line(self) -> None:
        """Process a single line of configuration."""
        current_version, latest_version = self.get_versions()
        comparison_result = semver.compare(current_version, latest_version)

        if comparison_result < 0:
            self.update_software()
        elif comparison_result == 0:
            print(
                f"No updates for {self.bin_dir}/{self.bin_name} version {current_version}"
            )
        else:
            logger.error("URL error for %s", self.bin_name)

    def get_semver_version(self, version: str) -> str:
        try:
            return semver.parse_version_info(version)
        except ValueError as _err:
            logger.error("SemVer '%s' parse error: %s", version, _err)

    def get_versions(self) -> Tuple[str, str]:
        """Set properties and get versions."""
        current_version = self.get_current_version().lstrip("v")
        pkg_repo_version = self.get_pkg_repo_version().lstrip("v")

        # Compare the two versions using semver.compare()
        comparison_result = semver.compare(current_version, pkg_repo_version)

        if comparison_result < 0:
            latest_version = pkg_repo_version
        else:
            latest_version = current_version

        return current_version, latest_version

    def get_current_version(self) -> str:
        """Get the current version of the binary."""
        if self.bin_version:
            return self.bin_version
        try:
            with timeout(10):
                cmd = subprocess.run(
                    [
                        f"{self.bin_dir}/{self.bin_name}",
                        self.bin_version_arg,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
        except (subprocess.CalledProcessError, TimeoutError) as _err:
            logger.error("Error running the command: %s", _err)
            return "0.0.0"

        pattern = r"v?(\d+\.\d+\.\d+(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?)"
        output = cmd.stdout.decode("utf-8")
        matches = re.findall(pattern, output)

        return matches[0][0] if matches else None

    def get_pkg_repo_version(self) -> str:
        if self.pkg_version:
            return self.pkg_version
        ghapi = GithubAPI(
            self.pkg_owner, self.pkg_repo, self.pkg_regex, self.gh_token, logger
        )
        return ghapi.get_response_from_github("version")

    def update_software(self, latest_version: str = None) -> None:
        """Updates software."""
        print(f"Update from {self.pkg_owner}/{self.pkg_repo}")
        download_url = self.get_download_url(latest_version)

        aria2 = API()
        aria2.download_from_url(
            download_url,
            out=f"{self.bin_name}.{self.pkg_type}",
            dir=self.tmp_dir,
            allow_overwrite=True,
            check_integrity=True,
            console_log_level="warn",
            continue_download=True,
            file_allocation="falloc",
            max_connection_per_server=6,
            remote_time=True,
        )
        if aria2.was_successful():
            print(
                f"Download {self.pkg_owner}/{self.pkg_repo} -> {self.tmp_dir} complete"
            )
            self.install_software()
        else:
            logger.error("Download error %s", self.bin_name)

    def get_download_url(self, latest_version: str) -> str:
        """Get the download URL by replacing the placeholder with the latest version."""
        if self.pkg_url:
            return self.pkg_url.replace("%VERSION%", latest_version)
        ghapi = GithubAPI(
            self.pkg_owner, self.pkg_repo, self.pkg_regex, self.gh_token, logger
        )
        return ghapi.get_response_from_github("asset")

    def install_software(self) -> None:
        """Install software."""
        if self.pkg_type == "bin":
            os.rename(
                f"{self.tmp_dir}/{self.bin_name}.{self.pkg_type}",
                f"{self.bin_dir}/{self.bin_name}",
            )
            os.chmod(f"{self.bin_dir}/{self.bin_name}", 0o755)
        elif self.pkg_type == "deb":
            try:
                subprocess.run(
                    [
                        "sudo",
                        "apt",
                        "install",
                        "--assume-yes",
                        f"{self.tmp_dir}/{self.bin_name}.{self.pkg_type}",
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as _err:
                logger.error("Error installing the package: %s", _err)
        elif self.pkg_type in ["zip", "tbz", "tgz", "txz", "gz"]:
            self.extract_and_install_archive()
        else:
            logger.error("Error with %s/%s", self.bin_dir, self.bin_name)

    def extract_and_install_archive(self) -> None:
        """Extract and install an archive."""
        try:
            subprocess.run(
                [
                    "unar",
                    "-f",
                    "-q",
                    "-d",
                    "-o",
                    self.tmp_dir,
                    f"{self.tmp_dir}/{self.bin_name}.{self.pkg_type}",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as _err:
            logger.error("Error extracting the archive: %s", _err)
            # Handle the error, for example, by raising a custom exception or returning an error value.
        else:
            # Continue with the processing if the command was successful.
            files = os.listdir(self.tmp_dir)
            for f in files:
                if f.startswith(self.bin_name) and not f.endswith(
                    f"{self.bin_name}.{self.pkg_type}"
                ):
                    os.rename(f"{self.tmp_dir}/{f}", f"{self.bin_dir}/{self.bin_name}")
                    os.chmod(f"{self.bin_dir}/{self.bin_name}", 0o755)


if __name__ == "__main__":
    DEBUG: str = os.environ.get("DEBUG") or None
    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Download and update packages from GitHub."
    )
    parser.add_argument(
        "--config",
        default=f"{os.environ['HOME']}/.config/getlatest.yml",
        type=argparse.FileType("r"),
        help="Config file",
    )
    parser.add_argument(
        "--regex",
        default="",
        help="Regular expression to select which packages should get updates.",
    )
    args: argparse.Namespace = parser.parse_args()

    gh_token: str = os.environ.get("GITHUB_TOKEN")
    tmp_dir: str = "/tmp/getlatest"
    getlatest_config: str = args.config.name
    update_only_regex: dict = re.compile(args.regex)

    os.makedirs(tmp_dir, exist_ok=True)

    try:
        with args.config as config_file:
            data = yaml.safe_load(config_file)
            for d in data:
                if any(update_only_regex.search(value) for value in d.values()):
                    print("---")
                    updater = GithubUpdater(gh_token, tmp_dir, logger, **d)
                    updater.process_line()
    except Exception as _err:
        logger.error("Error occurred while processing: %s", _err)
