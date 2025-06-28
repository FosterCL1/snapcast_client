## Hawkbit Server Setup

A local Hawkbit server is needed.
To achieve this, clone the Hawkbit server repo and start the container.

```
$ git clone https://github.com/eclipse-hawkbit/hawkbit.git
$ cd hawkbit/docker/postgres
$ docker-compose -f docker-compose-monolith-postgres.yml up -d
```

Then start the UI with the following container:

```
$ docker-compose -f docker-compose-monolith-with-simple-ui-dbinit-postgres.yml up -d
```

The UI should be accessible via the IP address, port 8088, with user/password
admin/admin.
