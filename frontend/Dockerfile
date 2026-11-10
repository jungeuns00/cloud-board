# 비root(uid 101)로 8080 포트에서 동작하는 nginx 이미지
FROM nginxinc/nginx-unprivileged:1.27-alpine

ENV BACKEND_URL=http://backend:8000

# /etc/nginx/templates/*.template 은 시작 시 envsubst 를 거쳐 conf.d 로 생성된다
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 8080
