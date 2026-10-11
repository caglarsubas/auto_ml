ARG NGINX_IMAGE
FROM ${NGINX_IMAGE}
# Exact trusted upstream digest selected by the packaging tool; no runtime
# templates, environment substitution, downloads or inherited entrypoint.
USER root
RUN addgroup -g 10001 declarai && adduser -D -H -u 10001 -G declarai declarai
COPY nginx.conf /etc/nginx/nginx.conf
COPY start-ingress.sh /opt/declarai/start-ingress.sh
USER 10001:10001
EXPOSE 8443
ENTRYPOINT ["/bin/sh", "/opt/declarai/start-ingress.sh"]
CMD []
