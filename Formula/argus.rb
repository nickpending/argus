class Argus < Formula
  include Language::Python::Virtualenv

  desc "Centralized local-network observability platform for development tools"
  homepage "https://github.com/nickpending/argus"
  url "https://github.com/nickpending/argus/releases/download/v0.1.0/argus-0.1.0.tar.gz"
  sha256 "110f12681b2303ccba7c63b8296ce4322421ff97a36c440b16a554ba117f24a4"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      Initialize Argus configuration:
        argus config init

      Start the Argus server:
        argus serve

      Access the web UI at http://127.0.0.1:8765
    EOS
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/argus --version")
  end
end
