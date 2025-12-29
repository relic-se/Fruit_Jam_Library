# Contributing

So, you've built a Fruit Jam application and you're ready to share it with the world? That's great! This guide will walk you through the steps of setting up your GitHub code repository, appending it to the library database, and creating a pull request to get the database updated.

## 1. Setup your application's GitHub repository

GitHub is imperative to the operation of the library. All application assets are queried and downloaded from public GitHub repositories. If you would like your application included in the library, you will need to publish it within a public git repository.

### Optional: Create your first release!

The library can pull source code directly from your code repository, but if your application requires libraries which aren't included with Fruit Jam OS or you want to have better versioning control of your application, it's recommend that you utilize GitHub's release system.

If you've followed the actions format in the [Fruit_Jam_Application](https://github.com/relic-se/Fruit_Jam_Application) template and [enabled GitHub Actions on your repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository), it will automatically package your application for the latest CircuitPython versions with all included libraries determined by `requirements.txt`.

## 2. Create your own fork of Fruit_Jam_Library

Unless you already have a fork of this repository within your GitHub account, follow [this guide](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) to create your own fork.

Once you've got your fork created, you'll want to clone it onto your local machine so that you can begin working within the repository. You can do this by following [this guide](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository).

## 4. Create a new branch within your fork

So now that you have your copy of the library, you'll want to split out into your own branch. There are a number of ways to do this depending on your environment, but we'll cover the CLI implementation here:

``` bash
cd Fruit_Jam_Library
git checkout -b {YOUR_BRANCH_NAME}
```

This should create a new branch with your specified name (it's recommended that you use a variant of your application's name) and switch over to it in one fell swoop.

## 3. Add your repository to the applications database

The database, found at [database/applications.json](applications.json) is formatted as a JSON file and sorted into categories. At this time, there are 4 categories: Games, Music, Utilities, and Video. If you feel that your application doesn't fit into any of the available categories, you can add a new category object key to the top level with your application in a new array.

_Note: Try to keep your application organized alphabetically by title!_

## 4. Update the database README

The library has a system in place to automatically provide updated details on each application within the [database README](README.md). So, it isn't required (nor recommended) for you manually update the database listing for your application.

In order to run the build script, you will need to have [Python 3](https://www.python.org/) with PIP support configured on your system. Then, you should be able to follow the following script to install all dependencies and rebuild the database listings:

``` bash
cd Fruit_Jam_Library
pip3 install -r database/requirements.txt
python3 database/build.py
```

## 5. Commit your changes

In order to update your branch with your latest changes, you'll need to commit those changes. We'll demonstrate the way to do this via the git CLI here, but it's recommended to use an application such as [Github Desktop](https://desktop.github.com/) to have a better visualization of the process.

``` bash
git status
git add --all
git commit -m "Added {YOUR_APPLICATION_NAME}"
```

## 6. Publish your branch

You may have noticed that your changes aren't visible on your fork on GitHub just yet. That's because we need to publish your new branch and push all of the committed changes you've made. This is easy to do with a single command:

``` bash
git push --set-upstream origin {YOUR_BRANCH_NAME}
```

Now, if you view your repository on GitHub, it should show your new branch and the commit that you published.

## 7. Create your pull request

In order to merge your changes with the main repository so that your application is visible to all users, you will need to create a pull request from your branch into [relic-se/Fruit_Jam_Library](https://github.com/relic-se/Fruit_Jam_Application) which will then undergo review before being accepted into the library.

You can follow [this guide](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request) to learn how to use GitHub's interfaces to create the pull request.

Don't worry too much about the description of the pull request. It doesn't hurt to talk a little about your application and any special considerations which may need to be made, but that isn't necessary.

## You're done!

Just wait for final review of your pull request. A moderator may request additional changes before final acceptance.

Once again, thank you for your interest in sharing your application with the library!
