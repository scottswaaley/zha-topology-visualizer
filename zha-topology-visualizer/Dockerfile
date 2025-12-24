ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies via pip (base-python image already has pip)
RUN pip3 install --no-cache-dir aiohttp pyyaml

# Copy root filesystem
COPY rootfs /

# Set working directory
WORKDIR /app

# Make scripts executable
RUN chmod a+x /run.sh

# Run as the entry point
ENTRYPOINT ["/run.sh"]
