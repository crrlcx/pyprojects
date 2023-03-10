# Recursively clone a group of repositories from GitLab

[[_TOC_]]

This script is useful for automating the cloning of multiple repositories from GitLab,  
especially when dealing with a large number of repositories.  
Repositories will be cloned using their respective SSH links.

## Alternatives

More powerful and popular alternatives:

- written on Python [gitlabber](https://github.com/ezbz/gitlabber)
- written on GoLang [ghorg](https://github.com/gabrie30/ghorg)

## Config file

Create ~/.python-gitlab.cfg with the following contents:

```ini
[gitlab]
url = https://gitlab.com
api_version = 4
private_token = token-tokenxxxxxxxxxxxx
```

## ENV variables

Also you can set name of config section or credentials as Env variables:

- config section name in ~/.python-gitlab, default is None

```shell
export GL_CONFIG_SECTION=gitlab
```

- or credentials, default is 'https://gitlab.com' and 'token'

```shell
export GL_URL=http://gitlab.com
export GL_TOKEN=token-tokenxxxxxxxxxxxx
```

- GitLab root path of group of projects, default None, ask it interactive if unset

```shell
export GL_ROOT_PATH="namespace/projects"
```

- Local base path of cloned repositories, default directory of scrypt

```shell
export GL_LOCAL_BASE_PATH=/path/to/repositories

```
