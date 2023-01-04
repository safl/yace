PROJECT=yace
TOOLBOX_PATH=toolbox

define default-help
# invoke: 'make uninstall', 'make install'
endef
.PHONY: default
default: build
	@echo "## ${PROJECT}: make default"
	@echo "## ${PROJECT}: make default [DONE]"

define all-help
# Do all: clean uninstall build install
endef
.PHONY: all
all: uninstall clean build install emit doxy

define all-system-help
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
# uninstall - Prefix with 'sudo' when uninstalling a system-wide installation
endef
.PHONY: uninstall
uninstall:
	@echo "## ${PROJECT}: make uninstall"
	@python3 -m pip uninstall ${PROJECT} --yes || echo "Cannot uninstall => That is OK"
	@echo "## ${PROJECT}: make uninstall [DONE]"

define install-system-help
# install system-wide
endef
.PHONY: install-system
install-system:
	@echo "## ${PROJECT}: make install-system"
	@python3 -m pip install dist/*.tar.gz
	@echo "## ${PROJECT}: make install-system [DONE]"

define clean-help
# clean build artifacts (build, dist, output)
endef
.PHONY: clean
clean:
	rm -r build || true
	rm -r dist || true
	rm -r output || true

define emit-xnvme-help
# Emit code using the xNVMe interface model
endef
.PHONY: emit-xnvme
emit-xnvme:
	yace models/xnvme.yaml
	clang-format --style=file:$(TOOLBOX_PATH)/clang-format-h -i output/*.h

define emit-nvme-help
# Emit code using the NVMe interface model
endef
.PHONY: emit-nvme
emit-nvme:
	yace models/nvme.yaml
	clang-format --style=file:$(TOOLBOX_PATH)/clang-format-h -i output/*.h

define emit-help
# Emit code using the example interface model
endef
.PHONY: emit
emit:
	yace models/example.yaml
	clang-format --style=file:$(TOOLBOX_PATH)/clang-format-h -i output/*.h

define view-help
# Inspect generated code
endef
.PHONY: view
view:
	less output/*

define doxy-help
# Inspect generated code
endef
.PHONY: doxy
doxy:
	doxygen output/doxy.cfg
	mv doxyreport output/

define release-build-help
# Produce Python distribution (sdist, bdist_wheel)
endef
.PHONY: release-build
release-build:
	python setup.py sdist
	python setup.py bdist_wheel

define release-upload-help
# Upload Python distribution (sdist, bdist_wheel)
endef
.PHONY: release-upload
release-upload:
	twine upload dist/*

define release-upload-help
# Produce + Upload Python distribution (sdist, bdist_wheel)
endef
.PHONY: release
release: clean release-build release-upload
	@echo -n "# rel: "; date

define docs-build-help
# generate documentation
endef
.PHONY: docs-build
docs-build:
	cd docs && rm -rf build
	cd docs && make html

define docs-view-help
# open the HTML
endef
.PHONY: docs-view
docs-view:
	open docs/build/html/index.html

define docs-help
# generate documentation and open the HTML
endef
.PHONY: docs
docs: docs-build docs-view

define format-help
# run code format (style, code-conventions and language-integrity) on staged changes
endef
.PHONY: format
format:
	@echo "## ${PROJECT}: format"
	@pre-commit run
	@echo "## ${PROJECT}: format [DONE]"

define format-all-help
# run code format (style, code-conventions and language-integrity) on all files
endef
.PHONY: format-all
format-all:
	@echo "## ${PROJECT}: format-all"
	@pre-commit run --all-files
	@echo "## ${PROJECT}: format-all [DONE]"

define help-help
# Print the description of every target
endef
.PHONY: help
help:
	@./$(TOOLBOX_PATH)/print_help.py --repos .
