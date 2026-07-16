FROM pandoc/extra@sha256:a1fcbb4ef0ff0433fdfaf9f19fcbd3440c4f53379327985d5107ac76227c5f1d

USER root
ARG QPDF_VERSION=12.0.0
ARG QPDF_SHA256=7380fe9d5b612a6c912cbf3a5875d9e27c20db6c559ebca51360da5125f351b8
COPY requirements.txt /tmp/renderer-requirements.txt
COPY npm/package.json npm/package-lock.json /opt/mermaid/

ENV TZ=UTC \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser \
    PUPPETEER_SKIP_DOWNLOAD=true

RUN apk add --no-cache \
      bash=5.2.37-r0 \
      chromium=136.0.7103.113-r0 \
      cmake=3.31.1-r0 \
      font-noto-cjk=0_git20220127-r1 \
      fontconfig=2.15.0-r1 \
      g++=14.2.0-r4 \
      libjpeg-turbo-dev=3.0.4-r0 \
      make=4.4.1-r2 \
      nodejs=22.23.0-r0 \
      npm=10.9.1-r0 \
      openssl-dev=3.3.7-r0 \
      pango=1.54.0-r1 \
      poppler-utils=24.02.0-r2 \
      py3-pip=24.3.1-r0 \
      py3-virtualenv=20.28.0-r0 \
      python3=3.12.12-r0 \
      zlib-dev=1.3.2-r0 \
  && python3 -m venv /opt/renderer-venv \
  && /opt/renderer-venv/bin/pip install --no-cache-dir \
      --requirement /tmp/renderer-requirements.txt \
  && npm ci --prefix /opt/mermaid --omit=dev --ignore-scripts \
  && ln -s /opt/mermaid/node_modules/.bin/mmdc /usr/local/bin/mmdc \
  && wget -q "https://github.com/qpdf/qpdf/releases/download/v${QPDF_VERSION}/qpdf-${QPDF_VERSION}.tar.gz" -O /tmp/qpdf.tar.gz \
  && echo "${QPDF_SHA256}  /tmp/qpdf.tar.gz" | sha256sum -c - \
  && tar -xzf /tmp/qpdf.tar.gz -C /tmp \
  && cmake -S "/tmp/qpdf-${QPDF_VERSION}" -B /tmp/qpdf-build \
      -DCMAKE_BUILD_TYPE=Release -DBUILD_STATIC_LIBS=OFF -DREQUIRE_CRYPTO_NATIVE=ON \
  && cmake --build /tmp/qpdf-build --target qpdf --parallel 2 \
  && install -m 0555 /tmp/qpdf-build/qpdf/qpdf /usr/local/bin/qpdf \
  && install -m 0555 /tmp/qpdf-build/libqpdf/libqpdf.so.30.0.0 /usr/local/lib/libqpdf.so.30.0.0 \
  && ln -s libqpdf.so.30.0.0 /usr/local/lib/libqpdf.so.30 \
  && ln -s libqpdf.so.30 /usr/local/lib/libqpdf.so \
  && rm -rf /tmp/qpdf* /root/.npm \
  && apk del cmake g++ libjpeg-turbo-dev make openssl-dev zlib-dev \
  && fc-cache -f
ENV PYTHONHASHSEED=0

COPY render.py pdf_inspect.py inventory.py /renderer/
COPY puppeteer-config.json /renderer/puppeteer-config.json
RUN chmod 0555 /renderer/render.py /renderer/pdf_inspect.py /renderer/inventory.py \
  && ln -s /renderer/render.py /renderer/render \
  && ln -s /renderer/pdf_inspect.py /renderer/inspect \
  && /renderer/inventory.py --write /renderer/inventory.json /renderer/inventory.sha256

ENV PATH=/opt/renderer-venv/bin:/usr/local/bin:/usr/bin:/bin
WORKDIR /work
ENTRYPOINT []
CMD ["/renderer/inventory.py"]
