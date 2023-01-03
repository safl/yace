PROJECT=yace

define default-help
# invoke: 'make uninstall', 'make install'
endef
.PHONY: default
default: build
	@echo "## ${PROJECT}: make default"
	@echo "## ${PROJECT}: make default [DONE]"

define  all-help
# Do all: clean uninstall build install
endef
.PHONY: all
all: uninstall clean build install emit doxy

define  all-system-help
# Do all: clean uninstall build install-system
endef
.PHONY: all-system
all-system: uninstall clean build install emit doxy

define build-help
# Build the package (source distribution package)
endef
.PHONY: build
build:
	@echo "## ${PROJECT}: make build-sdist"
	@python3 setup.py sdist
	@echo "## ${PROJECT}: make build-sdist [DONE]"

define install-help
# install for current user
endef
.PHONY: install
install:
	@echo "## ${PROJECT}: make install"
	@python3 -m pip install dist/*.tar.gz --user --no-build-isolation
	@echo "## ${PROJECT}: make install [DONE]"

define uninstall-help
# uninstall
#
# Prefix with 'sudo' when uninstalling a system-wide installation
endef
.PHONY: uninstall
uninstall:
	@echo "## ${PROJECT}: make uninstall"
	@python3 -m pip uninstall ${PROJECT} --yes || echo "Cannot uninstall => That is OK"
	@echo "## ${PROJECT}: make uninstall [DONE]"

define install-system-help
# install system-wide
#
# install system-wide
endef
.PHONY: install-system
install-system:
	@echo "## ${PROJECT}: make install-system"
	@python3 -m pip install dist/*.tar.gz
	@echo "## ${PROJECT}: make install-system [DONE]"

.PHONY: clean
clean:
	rm build/* || true
	rm dist/* || true
	rm -r output/* || true

.PHONY: emit-xnvme
emit-xnvme:
	yace --meta models/meta-xnvme.yaml --model models/xnvme  --templates templates/c
	clang-format --style=file:toolbox/clang-format-h -i output/*.h

.PHONY: emit-nvme
emit-nvme:
	yace --meta models/meta-nvme.yaml --model models/nvme  --templates templates/c
	clang-format --style=file:toolbox/clang-format-h -i output/*.h

.PHONY: emit
emit:
	yace --meta models/meta-example.yaml --model models/example  --templates templates/c
	clang-format --style=file:toolbox/clang-format-h -i output/*.h

.PHONY: view
view:
	less output/*

.PHONY: doxy
doxy:
	doxygen output/doxy.cfg
	mv doxyreport output/

.PHONY: release-build
release-build:
	python setup.py sdist
	python setup.py bdist_wheel

.PHONY: release-upload
release-upload:
	twine upload dist/*

.PHONY: release
release: clean release-build release-upload
	@echo -n "# rel: "; date

.PHONY: docs-build
docs-build:
	cd docs && rm -rf build
	cd docs && make html

.PHONY: docs-view
docs-view:
	open docs/build/html/index.html

.PHONY: docs
docs: docs-build docs-view

.PHONY: format
format:
	@echo "## ${PROJECT}: format"
	@pre-commit run
	@echo "## ${PROJECT}: format [DONE]"

define format-all-help
# run code format (style, code-conventions and language-integrity) on staged and committed changes
endef
.PHONY: format-all
format-all:
	@echo "## ${PROJECT}: format-all"
	@pre-commit run --all-files
	@echo "## ${PROJECT}: format-all [DONE]"
