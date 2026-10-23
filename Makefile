.PHONY: check test deb kali iso reassemble boot source fonts apps
check: test

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v
	node --test forks/code/test-features.cjs
	node --test forks/code/test-window-controls.mjs
	node scripts/desktop-tools-test.cjs
	python3 -m compileall -q src scripts forks build
	for script in packaging/*.sh scripts/*.sh build/*.sh; do bash -n "$$script" || exit; done

fonts:
	python3 scripts/build-fonts.py

apps:
	bash scripts/build-code.sh
	bash scripts/build-browser.sh

deb: fonts
	bash packaging/build-deb.sh

kali:
	bash scripts/build-kali.sh

iso:
	bash scripts/build-iso.sh

reassemble:
	bash scripts/reassemble-iso.sh

boot:
	bash scripts/rebuild-boot.sh

source:
	python3 scripts/package-source.py

