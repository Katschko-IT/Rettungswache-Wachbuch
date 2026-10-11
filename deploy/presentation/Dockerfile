FROM caddy:2.11.4-alpine
# Serving on 8080 needs no privileged-port file capability.
# Remove the upstream file capability so cap_drop ALL permits exec.
RUN setcap -r /usr/bin/caddy
COPY dist/ /srv/
COPY Caddyfile /etc/caddy/Caddyfile
# Archive extraction may create directories with mode 750. The rootless
# webserver must be able to traverse and read public static assets.
RUN chmod -R a+rX /srv
USER 65532:65532
EXPOSE 8080
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
