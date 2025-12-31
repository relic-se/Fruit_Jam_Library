#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright 2025 Cooper Dalrymple (@relic-se)
#
# SPDX-License-Identifier: MIT
import argparse
import json
import os
from pathlib import Path
import re

from github import Github, Repository, ContentFile
from mdutils.mdutils import MdUtils

DATABASE_FILE = "applications.json"
MARKDOWN_FILE = "README.md"

def main(reset: bool = False):
    db_dir = Path(__file__).parent

    # setup cache
    cache_dir = db_dir / ".cache"
    if reset and os.path.exists(cache_dir):
        os.rmdir(cache_dir)
    cache_dir.mkdir(exist_ok=True)

    def read_file(repo: Repository, filename: str, allow_empty: bool = True) -> str|object|list:
        print(f"Reading {filename}: ", end="")

        repo_dir = cache_dir / repo.full_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        path = repo_dir / filename
        is_json = filename.endswith(".json")

        if os.path.exists(path):
            with open(path, "r") as f:
                if is_json:
                    contents = json.load(f)
                else:
                    contents = f.read()
            print("Using cached result.")
        else:
            try:
                if (contents := (repo.get_readme() if filename == "README.md" else repo.get_contents(filename))):
                    contents = contents.decoded_content.decode("utf-8")
                if is_json and isinstance(contents, str):
                    contents = json.loads(contents)
            except Exception as e:
                if hasattr(e, "message") and e.message:
                    print(e.message)
                else:
                    print(e)
                contents = {} if is_json else ""
            else:
                print("Success!")
            finally:
                if allow_empty or contents:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with open(path, "w") as f:
                        if is_json:
                            json.dump(contents, f)
                        else:
                            f.write(contents)
        return contents

    # delete readme
    if os.path.isfile(db_dir / MARKDOWN_FILE):
        os.remove(db_dir / MARKDOWN_FILE)

    # read applications database
    print("Reading database")
    with open(db_dir / DATABASE_FILE, "r") as f:
        database = json.load(f)

    # connect with GitHub API
    print("Connecting with GitHub Web API")
    gh = Github()

    # setup README
    print("Beginning markdown file generation")
    md = MdUtils(file_name=str(db_dir / MARKDOWN_FILE))
    md.new_header(
        level=1,
        title="Applications Database",
    )
    md.new_line("Interested in contributing your Fruit Jam application? Read the [documention](./CONTRIBUTING.md) to learn more.")
    md.new_line()

    for category in database.keys():
        repositories = database[category]

        print(f"Generating category: {category}")
        md.new_header(
            level=2,
            title=category,
        )

        for repo_slug in repositories:
            # get repository
            print(f"Reading repository - {repo_slug}: ", end="")
            try:
                repo = gh.get_repo(repo_slug)
            except Exception as e:
                if hasattr(e, "message") and e.message:
                    print(e.message)
                else:
                    print(e)
                print("Skipping repository")
                continue
            else:
                print("Success!")
            raw_url = "https://raw.githubusercontent.com/{:s}/main".format(
                repo.full_name,
                repo.default_branch
            )

            # read repository readme (for title and screenshot)
            readme_contents = read_file(repo, "README.md")
            title = re.search(r'^# (.*)$', readme_contents, re.MULTILINE)
            title = title.group(1) if title is not None else repo.name

            # read Fruit Jam OS metadata
            metadata = read_file(repo, "metadata.json")
            if "title" in metadata:
                title = metadata["title"]
            icon = metadata["icon"] if "icon" in metadata else None

            # read build metadata
            build_metadata = read_file(repo, "build/metadata.json")
            guide_url = build_metadata["guide_url"] if "guide_url" in build_metadata else None
            
            # add application title
            md.new_header(
                level=3,
                title=(
                    "![{:s} icon]({:s}/{:s}) {:s}".format(
                        title,
                        raw_url,
                        icon,
                        title
                    ) if icon is not None else title
                ),
            )

            # add project description
            if repo.description:
                md.new_line(repo.description)
                md.new_line()

            # find screenshot in readme contents
            screenshot = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', readme_contents)
            if screenshot is not None:
                md.new_line(md.new_inline_image(
                    text=screenshot.group(1),
                    path=raw_url + "/" + screenshot.group(2),
                ))
                md.new_line()

            # create details table
            details = {}
            if repo.homepage:
                details["Website"] = repo.homepage
            if guide_url is not None:
                details["Playground Guide"] = f"[{guide_url}]({guide_url})"
            details["Latest Release"] = f"[Download]({repo.html_url}/releases/latest)"
            details["Code Repository"] = f"[{repo.full_name}]({repo.html_url})"
            details["Author"] = "[{:s}]({:s})".format(repo.owner.name if repo.owner.name is not None else repo.owner.login, repo.owner.html_url)

            details = list(map(lambda key: f"{key}: {details[key]}", details))
            md.new_list(details)
    
    # save file
    print("Saving markdown into {:s}".format(MARKDOWN_FILE))
    md.create_md_file()

    # close connection to GitHub API
    print("Closing GitHub Web API connection")
    gh.close()

    print("{:s} generation completed!".format(MARKDOWN_FILE))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--reset', action='store_true')
    args = parser.parse_args()

    main(reset=args.reset)
