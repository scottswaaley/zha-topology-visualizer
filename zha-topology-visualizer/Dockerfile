ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and pip, then install aiohttp via pip
RUN apk add --no-cache \
    python3 \
    py3-pip \
    && pip3 install --no-cache-dir --break-system-packages aiohttp

# Copy root filesystem
COPY rootfs /

# Set working directory
WORKDIR /app

# Make scripts executable
RUN chmod a+x /run.sh

# Run as the entry point
ENTRYPOINT ["/run.sh"]
