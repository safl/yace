PROJECT=yace
TOOLBOX_PATH=etal

ifeq ($(PLATFORM_ID),Windows)
else
PLATFORM_ID = $$( uname -s )
endif
PLATFORM = $$( \
	case $(PLATFORM_ID) in \
		( Linux | FreeBSD | OpenBSD | NetBSD | Windows | Darwin ) echo $(PLATFORM_ID) ;; \
		( * ) echo Unrecognized ;; \
	esac)


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
all: deps uninstall clean build install emit docs

define deps-help
# Install dependencies; this will install deps. via PyPI/pipx and system package-manager
#
# This assumes that you are running as a 'sudo' capable user on Ubuntu/Debian
endef
.PHONY: deps
deps:
	if [ "${PLATFORM_ID}" == "Darwin" ]; then ./etal/pkgs/macos.sh; else sudo ./etal/pkgs/ubuntu.sh; fi
	./etal/pkgs/python.sh

define docker-help
# drop into a docker instance with the repository bind-mounted at /tmp/yace
endef
.PHONY: docker
docker:
	@echo "## ${PROJECT}: docker"
	@docker run -it -w /tmp/${PROJECT} --mount type=bind,source="$(shell pwd)",target=/tmp/${PROJECT} debian:bookworm bash
	@echo "## ${PROJECT}: docker [DONE]"


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
	@pipx install dist/*.tar.gz
	@echo "## ${PROJECT}: make install [DONE]"

define uninstall-help
# uninstall - Prefix with 'sudo' when uninstalling a system-wide installation
endef
.PHONY: uninstall
uninstall:
	@echo "## ${PROJECT}: make uninstall"
	@pipx uninstall ${PROJECT} || echo "Cannot uninstall => That is OK"
	@echo "## ${PROJECT}: make uninstall [DONE]"

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
	yace models/xnvme.yaml --emit capi ctypes -l --output output/xnvme

define emit-nvme-help
# Emit code using the NVMe interface model
endef
.PHONY: emit-nvme
emit-nvme:
	yace models/nvme.yaml --emit capi ctypes -l --output output/nvme

define emit-example-help
# Emit code using the example interface model
endef
.PHONY: emit-example
emit-example:
	yace models/example.yaml --emit capi ctypes -l --output output/example

define emit-help
# Emit code for all examples
endef
.PHONY: emit
emit: emit-example emit-xnvme emit-nvme

define coverage-help
# Run emitter with coverage
endef
.PHONY: coverage
coverage:
	coverage erase
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace models/example.yaml --emit capi
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace models/example.yaml --format
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace models/example.yaml --lint
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace tests/parsing/foo.h --c-to-yace
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m pytest -v tests || true
	coverage report
	coverage html
	coverage lcov

define view-help
# Inspect generated code
endef
.PHONY: view
view:
	less output/*

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

define docs-build-prep-help
# Install Sphinx Doc. in a pipx-venv along with jinja2, pygments-ansi-color, and sphinxcontrib-gtagjs
endef
.PHONY: docs-build-prep
docs-build-prep:
	pipx install sphinx
	pipx inject sphinx jinja2
	pipx inject sphinx pygments-ansi-color
	pipx inject sphinx sphinxcontrib-gtagjs
	pipx inject sphinx furo
	pipx inject sphinx dist/*.tar.gz

define docs-build-help
# generate documentation
endef
.PHONY: docs-build
docs-build:
	$(shell pipx environment -v PIPX_LOCAL_VENVS)/sphinx/bin/python ./etal/gen_entity_index.py > docs/source/idl/list.rst
	cd docs && rm -rf build
	cd docs/source/install && kmdo .
	cd docs/source/usage && kmdo .
	cd docs/source/targets/capi && kmdo .
	cd docs/source/idl && kmdo .
	cd docs/source/codebase && kmdo .
	cd docs && make html

define docs-view-help
# open the HTML version documentation
endef
.PHONY: docs-view
docs-view:
	open docs/build/html/index.html

define docs-help
# generate documentation and open the HTML
endef
.PHONY: docs
docs: docs-build-prep docs-build

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

define bump-help
# run code format (style, code-conventions and language-integrity) on all files
endef
.PHONY: bump
bump:
	@echo "## ${PROJECT}: bump"
	@./$(TOOLBOX_PATH)/bump.py
	@echo "## ${PROJECT}: bump [DONE]"

define help-help
# Print the description of every target
endef
.PHONY: help
help:
	@./$(TOOLBOX_PATH)/mkhelp.py --repos .
