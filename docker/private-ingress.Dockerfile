ARG NGINX_IMAGE
FROM ${NGINX_IMAGE}
# Exact trusted upstream digest selected by the packaging tool; no runtime
# templates, environment substitution, downloads or inherited entrypoint.
USER root
RUN addgroup -g 10001 declarai && adduser -D -H -u 10001 -G declarai declarai
# Create the traversable parent before COPY applies read-only file modes.
RUN mkdir -p /opt/declarai && chmod 0755 /opt/declarai
# Replace the upstream public welcome page; serve only sealed allowlisted assets.
RUN rm -rf /usr/share/nginx/html
COPY --chmod=0444 nginx.conf /etc/nginx/nginx.conf
COPY --chmod=0444 start-ingress.sh /opt/declarai/start-ingress.sh
COPY --chown=10001:10001 frontend /opt/declarai/frontend
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["/bin/sh", "/opt/declarai/start-ingress.sh"]
CMD []
