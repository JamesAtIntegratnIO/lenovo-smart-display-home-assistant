{
  description = "Tools for unlocking the Lenovo Smart Display 7 (CD-17302F)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAllSystems (pkgs:
        let
          # at_auth_unlock.py (AVB unlock) needs PyCrypto's `Crypto` module;
          # ha_ws.py (Home Assistant dashboards) needs websockets and yaml
          avbPython = pkgs.python3.withPackages (ps: [ ps.pycryptodome ps.websockets ps.pyyaml ]);
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              android-tools # adb, fastboot
              unzip
            ];
            # android-tools puts its own python3 first on PATH, so expose ours by name
            shellHook = ''
              export AVB_PYTHON=${avbPython}/bin/python3
            '';
          };
        });
    };
}
