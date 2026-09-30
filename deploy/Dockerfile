# Containerized counterpart of deploy/nginx.conf (the bare-metal config for
# App Dev Plan D0). `server_name _` is a catch-all so this works unchanged
# behind an IP, a domain, or another load balancer in front — swap in a real
# server_name + TLS (certbot or an external LB) once you have one.
FROM nginx:1.27-alpine

RUN cat <<'EOF' > /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;
    client_max_body_size 25m;

    # Next.js
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Django API
    location /api/ {
        proxy_pass http://backend:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;  # engine refresh/replay actions
    }

    location /static/ { alias /srv/clausechain/backend/staticfiles/; }
    location /media/  { alias /srv/clausechain/backend/media/; }

    # Pre-rendered source-proof pages (public statutes; read-only)
    location /proof/ {
        alias /srv/clausechain/engine/submission/review/assets/;
        add_header Cache-Control "public, max-age=3600";
    }
}
EOF
