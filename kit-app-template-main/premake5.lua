-- Shared build scripts from repo_build package.
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Run repo_kit_tools premake5-kit that includes a bunch of Kit-friendly tooling configuration.
kit = require("_repo/deps/repo_kit_tools/kit-template/premake5-kit")
kit.setup_all({ cppdialect = "C++17" })


-- Registries config for testing
repo_build.prebuild_copy {
    { "%{root}/tools/deps/user.toml", "%{root}/_build/deps/user.toml" },
}

-- Apps: for each app generate batch files and a project based on kit files (e.g. my_name.my_app.kit)

define_app("younite.usd_composer.kit")
-- Streaming base: shared settings + production deps. Launch directly for production.
-- Dev (younite.usd_viewer_streaming_dev.kit) is a thin layer on top with extra extensions.
define_app("younite.usd_viewer_streaming_base.kit")
define_app("younite.usd_viewer_streaming_dev.kit")