"""Install the startup registration hook alongside the package in site-packages."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        self.hook_path.write_text(
            "import broditech_odoo_migrations.bootstrap; "
            "broditech_odoo_migrations.bootstrap.register()\n",
            encoding="utf-8",
        )

    @property
    def hook_path(self):
        return Path(self.build_lib) / "broditech_odoo_migrations_autoload.pth"

    def get_outputs(self, include_bytecode=1):
        return super().get_outputs(include_bytecode) + [str(self.hook_path)]


setup(cmdclass={"build_py": BuildPy})
