# Build only with the allowlisted context emitted by private_api_package.py.
# The builder creates a unique local reference to the trusted dependency digest.
# Copy system paths into a fresh image, never inheriting application/data layers.
ARG DEPENDENCY_IMAGE
FROM ${DEPENDENCY_IMAGE} AS dependencies
FROM scratch
COPY --from=dependencies /usr /usr
COPY --from=dependencies /bin /bin
COPY --from=dependencies /sbin /sbin
COPY --from=dependencies /lib /lib
COPY --from=dependencies /etc /etc
COPY --from=dependencies /var/lib/dpkg /var/lib/dpkg
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROMETA_DISABLE=1 \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    MPLCONFIGDIR=/tmp/matplotlib CHROMA_PERSIST_DIR=/tmp/chroma RAG_MODE=lexical \
    OPENAI_API_KEY="" LLM_ENGINE_BASE_URL=http://127.0.0.1:9/v1
RUN mkdir -p /tmp /run /root /var/log && chmod 1777 /tmp \
    && groupadd --gid 10001 declarai \
    && useradd --uid 10001 --gid 10001 --home-dir /tmp --no-create-home --shell /usr/sbin/nologin declarai
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && pip check \
    && rm /tmp/requirements.lock
COPY app /app
RUN python /app/scripts/private_runtime_manifest.py create \
    && mkdir -p /run/declarai \
    && chown 10001:10001 /run/declarai && chmod 0750 /run/declarai
WORKDIR /app/backend
USER 10001:10001
ENTRYPOINT ["python", "/app/scripts/private_service.py"]
CMD ["api"]
