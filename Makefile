PROJECT=yace
AUX_PATH=toolbox
PIPX_LOCAL_VENVS=$(shell pipx environment --value PIPX_LOCAL_VENVS)

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
# Do all: uninstall clean install docs
endef
.PHONY: all
all: uninstall clean install docs

define docker-help
# drop into a docker instance with the repository bind-mounted at /tmp/yace
endef
.PHONY: docker
docker:
	@echo "## ${PROJECT}: docker"
	@docker run -it -w /tmp/${PROJECT} --mount type=bind,source="$(shell pwd)",target=/tmp/${PROJECT} debian:bookworm bash
	@echo "## ${PROJECT}: docker [DONE]"

define install-help
# install using pipx and the Python interpreter resolve to by 'python3'
endef
.PHONY: install
install:
	@echo "## ${PROJECT}: make install"
	@pipx install --python python3 --include-deps --force --editable .[dev]
	@pipx inject yace black --include-deps
	@pipx inject yace build --include-deps
	@pipx inject yace ipdb --include-deps
	@pipx inject yace isort --include-deps
	@pipx inject yace pytest --include-deps
	@echo "## ${PROJECT}: make install [DONE]"

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
# Run the example
endef
.PHONY: example
example:
	yace models/example.h --output output
	yace output/*.yaml --output output

define coverage-help
# Run emitter with coverage
endef
.PHONY: coverage
coverage:
	coverage erase
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace models/example.h --output output
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace models/example.yaml --emit capi --output output
	coverage run -a --omit "*ctypes_sugar.py" --source=yace -m yace tests/parsing/example.h --output output
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
	$(PIPX_LOCAL_VENVS)/yace/bin/python -m build --sdist
	$(PIPX_LOCAL_VENVS)/yace/bin/python -m build --wheel

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
# Install docs tooling and dependencies
endef
.PHONY: docs-build-prep
docs-build-prep: install
	pipx install docs/tooling --force
	pipx inject yace-docs --editable . --force

define docs-kmdo-help
# Generate command output using kmdo
endef
.PHONY: docs-kmdo-help
docs-kmdo:
	kmdo docs/src/codebase
	kmdo docs/src/ir
	kmdo docs/src/install
	kmdo docs/src/targets/capi
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
# run code format (style, code-conventions and language-integrity) on all files
endef
.PHONY: bump
bump:
	@echo "## ${PROJECT}: bump"
	@./$(AUX_PATH)/bump.py
	@echo "## ${PROJECT}: bump [DONE]"

define help-help
# Print the description of every target
endef
.PHONY: help
help:
	@./$(AUX_PATH)/mkhelp.py --repos .
