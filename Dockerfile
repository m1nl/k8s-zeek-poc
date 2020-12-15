ARG ZEEK_VERSION=3.2.3
ARG ZEEK_GPG_KEY=962FD2187ED5A1DD82FC478A33F15EAEF8CB8019

FROM debian:buster-slim as builder

ARG ZEEK_VERSION
ARG ZEEK_GPG_KEY

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL=C
ENV LANG=C

RUN mkdir -p /usr/src
WORKDIR /usr/src

ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN set -eux; \
  apt-get -q --fix-missing update; \
  apt-get -y --no-install-recommends install build-essential git gpg gpg-agent dirmngr curl bison flex gawk cmake swig libssl-dev libmaxminddb-dev libpcap-dev python3-dev libcurl4-openssl-dev zlib1g-dev libbind-dev libjemalloc-dev libkrb5-dev ca-certificates; \
  apt-get clean; \
  rm -rf /var/lib/apt/lists/*; \
  rm -rf /usr/share/man/*; \
  rm -rf /usr/share/doc/*; \
  rm -rf /var/tmp/*; \
  rm -rf /tmp/*; \
  find /var/log -type f -regex '.*\.\([0-9]\|gz\)$' -print0 | xargs -0 rm -f; \
  find /var/log -type f -print0 | xargs -0 truncate -s 0

RUN set -eux; \
  export GNUPGHOME="$(mktemp -d)"; \
  gpg --keyserver ha.pool.sks-keyservers.net --recv-keys ${ZEEK_GPG_KEY}; \
  curl -sSL "https://download.zeek.org/zeek-${ZEEK_VERSION}.tar.gz" -o zeek-${ZEEK_VERSION}.tar.gz; \
  curl -sSL "https://download.zeek.org/zeek-${ZEEK_VERSION}.tar.gz.asc" -o zeek-${ZEEK_VERSION}.tar.gz.asc; \
  gpg --verify zeek-${ZEEK_VERSION}.tar.gz.asc; \
  rm -rf "$GNUPGHOME" zeek-${ZEEK_VERSION}.tar.gz.asc; \
  tar -xzf zeek-${ZEEK_VERSION}.tar.gz; \
  cd zeek-${ZEEK_VERSION}; \
  ./configure --prefix=/usr/local/zeek-${ZEEK_VERSION} --enable-jemalloc --disable-broker-tests; \
  make -j$(nproc) install

FROM debian:buster-slim

ARG ZEEK_VERSION

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL=C
ENV LANG=C

ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN set -eux; \
  apt-get -q --fix-missing update; \
  apt-get -y --no-install-recommends install bash vim procps runit curl bind9-host dnsutils net-tools iproute2 python3 python3-dev python3-pip python3-setuptools python3-wheel pipenv geoip-database ca-certificates libpcap0.8 libssl1.1 libmaxminddb0 zlib1g libjemalloc2 libkrb5-3; \
  apt-get clean; \
  rm -rf /var/lib/apt/lists/*; \
  rm -rf /usr/share/man/*; \
  rm -rf /usr/share/doc/*; \
  rm -rf /var/tmp/*; \
  rm -rf /tmp/*; \
  find /var/log -type f -regex '.*\.\([0-9]\|gz\)$' -print0 | xargs -0 rm -f; \
  find /var/log -type f -print0 | xargs -0 truncate -s 0

RUN set -eux; \
  update-alternatives --install /usr/bin/python python /usr/bin/python3 1; \
  update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

COPY --from=builder /usr/local/zeek-${ZEEK_VERSION} /usr/local/zeek-${ZEEK_VERSION}

RUN ln -s /usr/local/zeek-${ZEEK_VERSION} /bro
RUN ln -s /usr/local/zeek-${ZEEK_VERSION} /zeek

COPY ./spool /zeek/spool

ENV PATH /zeek/bin:/zeek/share/zeekctl/scripts:$PATH
ENV ZEEKPATH /zeek/spool/site:/zeek/spool/auto:/zeek/share/zeek:/zeek/share/zeek/policy:/zeek/share/zeek/site
ENV makearchivename /zeek/share/zeekctl/scripts/make-archive-name

RUN mkdir -p /watch
COPY ./watch/Pipfile* /watch/

RUN set -eux; \
  cd /watch; \
  pipenv lock --requirements > requirements.txt; \
  pip install -r requirements.txt

COPY ./watch /watch

RUN touch /etc/inittab
COPY ./service /etc/service

COPY docker-entrypoint.sh /usr/local/sbin/docker-entrypoint.sh

CMD ["docker-entrypoint.sh"]
