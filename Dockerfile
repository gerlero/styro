ARG OPENFOAM_VERSION=latest
FROM microfluidica/openfoam:${OPENFOAM_VERSION}

ARG VIRTUAL_ENV=/opt/venv

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get -y install --no-install-recommends \
    python3-venv git \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv ${VIRTUAL_ENV}

ENV PATH="${VIRTUAL_ENV}/bin:$PATH"

COPY . /src/

RUN pip install --no-cache-dir /src \
# smoke test
 && styro --help \
 && rm -rf /src
