FROM mysql:8.0
RUN chown -R mysql:root /var/lib/mysql
ENV MYSQL_ROOT_HOST="%"
ENV LANG=C.UTF-8
COPY pokemon/01_reinit.sql /docker-entrypoint-initdb.d
CMD ["mysqld", "--bind-address=0.0.0.0"]
EXPOSE 3306