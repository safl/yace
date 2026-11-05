PROJECT=yace
AUX_PATH=toolbox
PIPX_LOCAL_VENVS=$(shell pipx environment --value PIPX_LOCAL_VENVS)
PYTEST=$(PIPX_LOCAL_VENVS)/$(PROJECT)/bin/pytest
PYTHON ?= python3
CONTAINER ?= $(shell command -v podman >/dev/null && echo podman || echo docker)
DEVENV ?= ghcr.io/safl/yace-devenv:$(shell toolbox/devenv/tag.sh)

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
default: help

define all-help
# Do all: uninstall clean deps build install test
endef
.PHONY: all
all: uninstall clean deps build install test

define deps-help
# Tools for building yace and uploading it to PyPI
endef
.PHONY: deps
deps:
	pipx install build || true
	pipx install twine || true

define build-help
# Build the package (sdist and wheel)
endef
.PHONY: build
build:
	@echo "## ${PROJECT}: make build"
	@pyproject-build
	@echo "## ${PROJECT}: make build [DONE]"

define devenv-help
# build the development environment, the image CI runs in, from toolbox/devenv
endef
.PHONY: devenv
devenv:
	@$(CONTAINER) build -f toolbox/devenv/Containerfile -t $(DEVENV) .

define devenv-pull-help
# pull the development environment of this tree from the registry
endef
.PHONY: devenv-pull
devenv-pull:
	@$(CONTAINER) pull $(DEVENV)

define devenv-push-help
# push the development environment to the registry
endef
.PHONY: devenv-push
devenv-push:
	@$(CONTAINER) push $(DEVENV)

DEVENV_RUN = $(CONTAINER) run --rm -v "$(CURDIR)":/yace -w /yace \
	$(if $(findstring podman,$(CONTAINER)),--userns=keep-id,--user $$(id -u):$$(id -g))

define devenv-shell-help
# a shell in the development environment, as your own user, the repository at /yace
endef
.PHONY: devenv-shell
devenv-shell:
	@$(DEVENV_RUN) -it $(DEVENV) bash

define devenv-run-help
# run CMD in the development environment, as devenv-shell would, e.g. CMD="make test"
endef
.PHONY: devenv-run
export CMD
devenv-run:
	@$(DEVENV_RUN) $(DEVENV) bash -c "$$CMD"

define install-help
# install the wheel from 'make build' using pipx, with what 'make test' needs
endef
.PHONY: install
install:
	@echo "## ${PROJECT}: make install"
	@pipx install --python $(PYTHON) --force dist/*.whl
	@pipx inject yace pytest pytest-cov coverage --force
	@echo "## ${PROJECT}: make install [DONE]"

define install-source-help
# install the source tree, editable, using pipx along with the dev tools
endef
.PHONY: install-source
install-source:
	@echo "## ${PROJECT}: make install-source"
	@pipx install --python $(PYTHON) --include-deps --force --editable .[dev]
	@pipx inject yace black --include-deps
	@pipx inject yace build --include-deps
	@pipx inject yace ipdb --include-deps
	@pipx inject yace isort --include-deps
	@pipx inject yace pytest pytest-cov --include-deps
	@echo "## ${PROJECT}: make install-source [DONE]"

define test-help
# run pytest, from the pipx environment of yace, with coverage
endef
.PHONY: test
test:
	@echo "## ${PROJECT}: make test"
	@$(PYTEST) --cov=yace --cov-branch tests
	@echo "## ${PROJECT}: make test [DONE]"

define uninstall-help
# uninstall via pipx
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

define example-help
# Parse the example library's header, strictly, then generate and check every target
endef
.PHONY: example
example:
	yace examples/libfoo/include/foo.h --meta examples/libfoo/meta.yaml --output output --emit capi python rust cpp zig go --strict

define docs-build-prep-help
# Install docs tooling and dependencies
endef
.PHONY: docs-build-prep
docs-build-prep: install-source
	pipx install docs/tooling --force
	pipx inject yace-docs --editable . --force

define docs-kmdo-help
# Generate command output using kmdo
endef
.PHONY: docs-kmdo-help
docs-kmdo: example
	kmdo docs/src/codebase
	kmdo docs/src/ir
	kmdo docs/src/install
	kmdo docs/src/targets/capi
	kmdo docs/src/targets/python
	kmdo docs/src/targets/rust
	kmdo docs/src/targets/cpp
	kmdo docs/src/targets/zig
	kmdo docs/src/usage

define docs-gen-entities-help
# Generate documentation of IR entities
endef
.PHONY: docs-gen-entities
docs-gen-entities:
	yace-docs-gen-entities

define docs-build-help
# generate documentation
endef
.PHONY: docs-build
docs-build:
	yace-docs-clean
	yace-docs-build-html

define docs-view-help
# open the HTML version documentation
endef
.PHONY: docs-view
docs-view:
	yace-docs-serve --open-browser

define docs-help
# generate documentation (command-output, section-gen, HTML) and open the HTML
endef
.PHONY: docs
docs: docs-build-prep docs-kmdo docs-gen-entities docs-build

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
# bump the patch version in src/yace/__init__.py
endef
.PHONY: bump
bump:
	@echo "## ${PROJECT}: bump"
	@./$(AUX_PATH)/bump.py
	@echo "## ${PROJECT}: bump [DONE]"

define survey-help
# Run yace parser survey across ~90 popular C libraries
endef
.PHONY: survey
survey:
	@echo "## ${PROJECT}: survey"
	@python3 ./$(AUX_PATH)/survey/survey.py
	@echo "## ${PROJECT}: survey [DONE]"

define help-help
# Print the description of every target
endef
.PHONY: help
help:
	@./$(AUX_PATH)/mkhelp.py --repos .
