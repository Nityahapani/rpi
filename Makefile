.PHONY: test demo init daily refresh refresh-offline weights audit probe official eval diag uncertainty lock replicate shadow
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
eval:     ; python3 -m rpi eval
diag:     ; python3 -m rpi diag
uncertainty: ; python3 -m rpi uncertainty
lock:     ; python3 -m pip freeze | grep -iE '^(pandas|numpy|scipy|matplotlib|requests|beautifulsoup4|lxml|pytest|pdfplumber)==' > requirements.lock.txt && cat requirements.lock.txt
replicate: ; python3 -m pytest -q && python3 -m rpi eval && python3 -m rpi diag
shadow:   ; python3 -m rpi shadow
