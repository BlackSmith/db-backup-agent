#!/usr/bin/env bash
set -e

# VSCode appearance
git config --replace-all devcontainers-theme.show-dirty 1

# Aliasy
echo "alias ll='ls -la'" >> ~/.bashrc
# echo -e "pip() { \n pushd /workspace/backend/ > /dev/null && pdm run pip \"\$@\" && popd > /dev/null \n}" >> ~/.bashrc
# echo -e "python() { \n pushd /workspace/backend/ > /dev/null && pdm run python \"\$@\" && popd > /dev/null \n}" >> ~/.bashrc


sudo apt update && sudo apt install --no-install-recommends -y curl ca-certificates bash-completion docker.io rsync \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | sudo bash - \
    && sudo apt update && sudo apt install --no-install-recommends -y  nodejs \
    && sudo npm install -g --ignore-scripts @earendil-works/pi-coding-agent \
    && sudo apt clean -y
