FROM python:3.13-slim

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
    less \
    git \
    openssh-client \
    procps \
    sudo \
    fzf \
    zsh \
    fish \
    man-db \
    unzip \
    gnupg2 \
    gh \
    iptables \
    ipset \
    iproute2 \
    dnsutils \
    aggregate \
    jq \
    nano \
    vim \
    curl \
    wget \
    build-essential \
    locales \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Configure locale to fix perl warnings
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Install uv package manager
RUN pip install --no-cache-dir uv

# Create python user
RUN groupadd --gid 1000 python && \
    useradd --uid 1000 --gid python --shell /bin/bash --create-home python

ARG USERNAME=python

# Persist bash, fish, and fzf history.
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir -p /commandhistory/.local/share/fish \
    && touch /commandhistory/.bash_history \
    && touch /commandhistory/.fzf_history \
    && chown -R $USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# Create workspace and config directories and set permissions
RUN mkdir -p /workspace /home/python/.claude && \
    chown -R python:python /workspace /home/python/.claude

WORKDIR /workspace

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
    wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Install Claude Code CLI via npm (keeping Node.js installation for this specific tool)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Set up non-root user
USER python

# Set the default shell to fish rather than sh
ENV SHELL=/usr/bin/fish

# Set the default editor and visual
ENV EDITOR=nano
ENV VISUAL=nano

# Default powerline10k theme
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
    -p git \
    -p fzf \
    -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
    -a "source /usr/share/doc/fzf/examples/completion.zsh" \
    -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    -x


# Copy and set up firewall script
COPY .devcontainer/init-firewall.sh /usr/local/bin/
USER root
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    echo "python ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/python-firewall && \
    chmod 0440 /etc/sudoers.d/python-firewall
USER python

# Install project dependencies
COPY pyproject.toml README.md ./
COPY src/ src/
RUN uv sync --dev

# Create container-safe fish config that preserves PATH and activates virtual environment
RUN mkdir -p /home/python/.config/fish && \
    echo "if status is-interactive" > /home/python/.config/fish/config.fish && \
    echo "    # Preserve container PATH for Claude CLI and other tools" >> /home/python/.config/fish/config.fish && \
    echo "    # Host functions will be available via mounted functions directory" >> /home/python/.config/fish/config.fish && \
    echo "    # Configure persistent history locations" >> /home/python/.config/fish/config.fish && \
    echo "    set -gx XDG_DATA_HOME /commandhistory/.local/share" >> /home/python/.config/fish/config.fish && \
    echo "    set -gx FZF_DEFAULT_OPTS \"--history=/commandhistory/.fzf_history\"" >> /home/python/.config/fish/config.fish && \
    echo "    # Activate uv virtual environment if it exists" >> /home/python/.config/fish/config.fish && \
    echo "    if test -f /workspace/.venv/bin/activate.fish" >> /home/python/.config/fish/config.fish && \
    echo "        source /workspace/.venv/bin/activate.fish" >> /home/python/.config/fish/config.fish && \
    echo "    end" >> /home/python/.config/fish/config.fish && \
    echo "    # Disable virtual environment prompt override since devcontainer is always in virtual environment" >> /home/python/.config/fish/config.fish && \
    echo "    set -gx VIRTUAL_ENV_DISABLE_PROMPT 1" >> /home/python/.config/fish/config.fish && \
    echo "    # Disable venv section since devcontainer is always in virtual environment" >> /home/python/.config/fish/config.fish && \
    echo "    set -gx SPACEFISH_VENV_SHOW false" >> /home/python/.config/fish/config.fish && \
    echo "end" >> /home/python/.config/fish/config.fish && \
    chown -R python:python /home/python/.config/fish