FROM python:3.13-slim

# Build arguments
ARG TZ
ARG CLAUDE_CODE_VERSION=latest
ARG GIT_DELTA_VERSION=0.18.2
ARG USERNAME=python

# Environment variables
ENV TZ="$TZ" \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    DEVCONTAINER=true \
    SHELL=/usr/bin/fish \
    EDITOR=vim \
    VISUAL=vim \
    PATH="/home/python/.local/bin:$PATH"

# Install all system packages and configure locale in single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    less \
    git \
    openssh-client \
    procps \
    sudo \
    fzf \
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
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create python user and necessary directories
RUN groupadd --gid 1000 python && \
    useradd --uid 1000 --gid python --shell /usr/bin/fish --create-home python && \
    mkdir -p /workspace /home/python/.claude /commandhistory/.local/share/fish && \
    touch /commandhistory/.fzf_history && \
    chown -R python:python /workspace /home/python/.claude /commandhistory

# Install package managers and tools
RUN pip install --no-cache-dir uv && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install git-delta
RUN ARCH=$(dpkg --print-architecture) && \
    wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
    rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Copy project files early for better layer caching
WORKDIR /workspace
COPY --chown=python:python pyproject.toml README.md ./
COPY --chown=python:python src/ src/

# Switch to python user for remaining operations
USER python

# Install project dependencies
RUN uv sync --dev

# Configure fish shell
RUN mkdir -p /home/python/.config/fish
COPY --chown=python:python .devcontainer/config.fish /home/python/.config/fish/config.fish

# Copy and set up firewall script (requires root)
USER root
COPY .devcontainer/init-firewall.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    echo "python ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/python-firewall && \
    chmod 0440 /etc/sudoers.d/python-firewall

# Final user switch
USER python
WORKDIR /workspace
