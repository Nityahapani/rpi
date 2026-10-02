.PHONY: test demo init daily refresh refresh-offline weights audit probe official
test:     ; python3 -m pytest -q
demo:     ; python3 -m rpi demo
init:     ; python3 -m rpi init
daily:    ; python3 -m rpi daily
refresh:  ; python3 -m rpi refresh
refresh-offline: ; python3 -m rpi refresh --offline
weights:  ; python3 -m rpi.weights_build
audit:    ; python3 -m rpi audit
probe:    ; python3 -m rpi probe
official: ; python3 -c "from rpi.collectors.mospi_cpi import fetch_cpi; fetch_cpi()"
