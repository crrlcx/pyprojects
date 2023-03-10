#!/usr/bin/env python3

"""
Recursively clone a group of repositories from GitLab.

This script is useful for automating the cloning or update
multiple repositories from GitLab, especially when dealing
with a large number of repositories.
Repositories will be cloned using their respective SSH links.

Please read documentation in `README.md`.

"""

import os
import sys
import signal
from multiprocessing import Pool
from functools import partial
import gitlab
from git import Repo, GitCommandError, InvalidGitRepositoryError


def auth_with_gitlab_credentials(gl_url: str, gl_token: str) -> gitlab.Gitlab:
    """
    This function takes two arguments gl_url and gl_token,
    which are the GitLab URL and access token respectively.
    It uses the gitlab module to authenticate with GitLab
    and returns the Gitlab object.
    """
    try:
        gl = gitlab.Gitlab(gl_url, private_token=gl_token)
        gl.auth()
        return gl
    except gitlab.exceptions.GitlabAuthenticationError as _err:
        print(f"Failed to authenticate with GitLab with credentials: {_err}")
        sys.exit(1)


def auth_with_gitlab_config(gl_config_section: str) -> gitlab.Gitlab:
    """
    This function takes one argument gl_config_section,
    which is the name of the config section in the ~/.python-gitlab.cfg file.
    It uses the gitlab module to authenticate with GitLab
    and returns the Gitlab object.
    """
    try:
        gl = gitlab.Gitlab.from_config(gl_config_section)
        gl.auth()
        return gl
    except (
        gitlab.exceptions.GitlabAuthenticationError,
        gitlab.config.GitlabDataError,
    ) as _err:
        print(f"Failed to authenticate with GitLab with config: {_err}")
        sys.exit(1)


def get_root_group_path(gl: gitlab.Gitlab, gl_root_path: str) -> str:
    """
    This function takes two arguments gl and gl_root_path,
    which are the Gitlab object and the root group path respectively.
    It uses the gitlab module to retrieve the root group path and returns it.
    """
    try:
        root_grp = gl.groups.get(gl_root_path)
        return root_grp
    except gitlab.exceptions.GitlabGetError as _err:
        print(f"Failed to find group path: {_err}\nPlease try again.")
        sys.exit(1)


def create_directory(path: str) -> None:
    """
    This function takes one argument path,
    which is the path to create a directory.
    It uses the os module to create a directory if it doesn't exist.
    """
    if not os.path.exists(path):
        os.makedirs(path)


def clone_repository(project: str, path: str, timeout: int) -> None:
    """
    This function takes two arguments project and path,
    which are the GitLab project and the path to clone
    the repository respectively.
    It first tries to fetch updates if the path is already
    a git repository, otherwise, it clones the repository
    using the ssh_url_to_repo property of the project.
    """
    # Fetch updates
    try:
        repo = Repo(path)
        print(f"'{path}' is git repository. Trying to fetch changes")
        signal.alarm(timeout)
        repo.remotes.origin.fetch()
        signal.alarm(0)
    except InvalidGitRepositoryError:
        pass
    except GitCommandError as _err:
        print(f"Failed to fetch changes: {_err}")
    else:
        return
    # Clone repository
    try:
        print(f"Cloning '{project.path_with_namespace}' to '{gl_local_base_path}'.")
        signal.alarm(timeout)
        Repo.clone_from(project.ssh_url_to_repo, path)
        signal.alarm(0)
    except GitCommandError as _err:
        print(f"Failed to cloning repository: {_err}")
        sys.exit(1)


if __name__ == "__main__":
    gl_batch = 10
    gl_timeout = 180

    gl_local_base_path = os.path.abspath(
        os.environ.get("GL_LOCAL_BASE_PATH", os.path.dirname(os.path.abspath(__file__)))
    )
    gl_root_path = os.environ.get("GL_ROOT_PATH") or input(
        "GL_ROOT_PATH environment variable not set.\nPlease enter the group, like 'namespace/projects': "
    )
    gl_config_section = os.environ.get("GL_CONFIG_SECTION") or None

    if not gl_config_section:
        gl_url = os.environ.get("GL_URL") or input("GitLab url: ")
        gl_token = os.environ.get("GL_TOKEN") or input("GitLab token: ")
        gl = auth_with_gitlab_credentials(gl_url, gl_token)
    else:
        gl = auth_with_gitlab_config(gl_config_section)

    try:
        root_grp = get_root_group_path(gl, gl_root_path)
        projects = root_grp.projects.list(include_subgroups=True, all=True)
    except (
        gitlab.exceptions.GitlabGetError,
        gitlab.exceptions.GitlabListError,
    ) as _err:
        print(f"Failed to retrieve information from GitLab: {_err}")
        sys.exit(1)

    pool = Pool(processes=os.cpu_count())
    for i in range(0, len(projects), gl_batch):
        batch = projects[i : i + gl_batch]
        results = []
        for project in batch:
            path = os.path.join(gl_local_base_path, project.path_with_namespace)
            create_directory(path)
            clone_func = partial(clone_repository, project, path, gl_timeout)
            result = pool.apply_async(clone_func)
            results.append(result)
        for result in results:
            result.wait()

    pool.close()
    pool.join()
