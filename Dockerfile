ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and aiohttp
RUN apk add --no-cache \
    python3 \
    py3-aiohttp

# Copy root filesystem
COPY rootfs /

# Set working directory
WORKDIR /app

# Make scripts executable
RUN chmod a+x /run.sh

CMD ["/run.sh"]
