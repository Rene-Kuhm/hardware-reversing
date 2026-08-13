{
  description = "RGB Fusion — Gigabyte motherboard LED controller for NixOS/Linux";

  inputs = {
    nixpkgs.url     = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # -----------------------------------------------------------------------
      # NixOS module — available as self.nixosModules.rgbFusion
      # -----------------------------------------------------------------------
      nixosModule = { config, lib, pkgs, ... }:
        let
          cfg = config.services.rgbFusion;

          # Build the rgb-fusion Python package from this flake's source
          rgbFusionPkg = self.packages.${pkgs.system}.rgb-fusion;

          # Render the TOML config file from NixOS options
          configFile = pkgs.writeText "rgb-fusion-config.toml" cfg.configText;
        in
        {
          # -------------------------------------------------------------------
          # Option declarations
          # -------------------------------------------------------------------
          options.services.rgbFusion = {

            enable = lib.mkEnableOption "RGB Fusion LED controller service";

            configFile = lib.mkOption {
              type        = lib.types.nullOr lib.types.path;
              default     = null;
              description = ''
                Path to an existing config.toml file.
                If null, <option>services.rgbFusion.configText</option> is used.
              '';
            };

            configText = lib.mkOption {
              type    = lib.types.lines;
              default = "";
              example = lib.literalExpression ''
                [[zone]]
                zone       = 0
                mode       = "breath"
                color      = "FF0000"
                speed      = 5
                brightness = 9
                led_count  = 60
              '';
              description = ''
                Inline TOML configuration written to
                <filename>/etc/rgb-fusion/config.toml</filename>.
                Mutually exclusive with
                <option>services.rgbFusion.configFile</option>.
              '';
            };

            daemonMode = lib.mkOption {
              type    = lib.types.bool;
              default = false;
              description = ''
                Run rgb-fusion as a persistent daemon that watches the config
                file and re-applies on changes.  When false (default), it runs
                once at boot and exits (Type=oneshot).
              '';
            };

            extraArgs = lib.mkOption {
              type    = lib.types.listOf lib.types.str;
              default = [];
              example = [ "--debug" "--bus" "3" ];
              description = "Additional arguments passed to the rgb-fusion command.";
            };

            i2cGroup = lib.mkOption {
              type    = lib.types.str;
              default = "i2c";
              description = ''
                The Unix group that owns /dev/i2c-* devices.
                The service runs as this group so root is not required.
              '';
            };
          };

          # -------------------------------------------------------------------
          # Implementation
          # -------------------------------------------------------------------
          config = lib.mkIf cfg.enable {

            # Ensure the i2c group exists
            users.groups.${cfg.i2cGroup} = {};

            # Kernel modules needed for I2C SMBus access
            boot.kernelModules = [ "i2c-dev" "i2c-i801" ];

            # udev rules: give the i2c group rw access to all i2c buses
            services.udev.extraRules = ''
              SUBSYSTEM=="i2c-dev", GROUP="${cfg.i2cGroup}", MODE="0660"
              SUBSYSTEM=="i2c",     GROUP="${cfg.i2cGroup}", MODE="0660"
            '';

            # Write config file to /etc/rgb-fusion/config.toml
            environment.etc."rgb-fusion/config.toml".source =
              if cfg.configFile != null
              then cfg.configFile
              else configFile;

            # Make the CLI available system-wide
            environment.systemPackages = [ rgbFusionPkg ];

            # systemd service
            systemd.services.rgb-fusion =
              let
                applyCmd = lib.escapeShellArgs (
                  [ "${rgbFusionPkg}/bin/rgb-fusion" ]
                  ++ cfg.extraArgs
                  ++ (
                    if cfg.daemonMode
                    then [ "daemon" "--config" "/etc/rgb-fusion/config.toml" ]
                    else [ "apply"  "--config" "/etc/rgb-fusion/config.toml" ]
                  )
                );
              in
              {
                description   = "RGB Fusion LED Controller";
                documentation = [ "https://github.com/your-user/rgb-fusion-nixos" ];

                wantedBy = [ "multi-user.target" ];
                after    = [ "systemd-udev-settle.service" ];
                requires = [ "systemd-udev-settle.service" ];

                serviceConfig = {
                  Type            = if cfg.daemonMode then "simple" else "oneshot";
                  RemainAfterExit = !cfg.daemonMode;
                  ExecStart       = applyCmd;

                  # Run as root (needed for i2c access before udev rule takes
                  # effect on first boot; alternatively add the service user to
                  # the i2c group and drop SupplementaryGroups = [ cfg.i2cGroup ])
                  User            = "root";

                  # Harden the service
                  NoNewPrivileges        = true;
                  ProtectSystem          = "strict";
                  ProtectHome            = true;
                  ReadWritePaths         = [ "/dev" ];
                  PrivateTmp             = true;
                  PrivateNetwork         = true;
                  RestrictAddressFamilies = [ "AF_UNIX" ];
                  SystemCallFilter       = [
                    "@system-service"
                    "ioctl"              # required for i2c-dev ioctls
                  ];

                  Restart    = if cfg.daemonMode then "on-failure" else "no";
                  RestartSec = "5s";
                };
              };
          };
        };

    in

    # -------------------------------------------------------------------------
    # Per-system outputs (packages, devShells, apps)
    # -------------------------------------------------------------------------
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        # Python environment with all required dependencies
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.smbus2
          ps.hid
          # tomllib is built-in for Python >= 3.11;
          # add tomli as a fallback for older interpreters
          (if pkgs.python3.pythonAtLeast "3.11" then ps.setuptools else ps.tomli)
        ]);

        rgbFusionPackage = pkgs.stdenv.mkDerivation {
          pname   = "rgb-fusion";
          version = "1.0.0";

          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];
          buildInputs       = [ pythonEnv ];

          installPhase = ''
            runHook preInstall

            install -Dm755 rgb_fusion.py $out/lib/rgb-fusion/rgb_fusion.py

            # Install example config
            install -Dm644 config.example.toml \
              $out/share/rgb-fusion/config.example.toml

            # Create the wrapper script that runs with the correct Python
            makeWrapper ${pythonEnv}/bin/python $out/bin/rgb-fusion \
              --add-flags "$out/lib/rgb-fusion/rgb_fusion.py"

            runHook postInstall
          '';

          meta = {
            description  = "Gigabyte RGB Fusion LED controller for Linux/NixOS";
            longDescription = ''
              Controls Gigabyte motherboard RGB LEDs via SMBus/I2C
              (IT8295/IT8297 chips) and USB HID external devices (AORUS).
              Includes a NixOS module with systemd service, udev rules,
              and kernel module configuration.
            '';
            homepage    = "https://github.com/your-user/rgb-fusion-nixos";
            license     = pkgs.lib.licenses.mit;
            maintainers = [];
            platforms   = pkgs.lib.platforms.linux;
          };
        };

      in
      {
        # Expose the package
        packages = {
          rgb-fusion = rgbFusionPackage;
          default    = rgbFusionPackage;
        };

        # Default app: run rgb-fusion directly with `nix run`
        apps = {
          rgb-fusion = {
            type    = "app";
            program = "${rgbFusionPackage}/bin/rgb-fusion";
          };
          default = {
            type    = "app";
            program = "${rgbFusionPackage}/bin/rgb-fusion";
          };
        };

        # Development shell: all deps + useful i2c tools
        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.i2c-tools     # i2cdetect, i2cget, i2cset, i2cdump
            pkgs.usbutils      # lsusb
            pkgs.python3Packages.black
            pkgs.python3Packages.mypy
            pkgs.python3Packages.pytest
          ];

          shellHook = ''
            echo "RGB Fusion dev shell"
            echo "  i2cdetect -l          — list I2C buses"
            echo "  i2cdetect -y <bus>    — scan bus for devices"
            echo "  python rgb_fusion.py list"
            echo ""
          '';
        };
      }
    )

    //

    # -------------------------------------------------------------------------
    # System-independent outputs
    # -------------------------------------------------------------------------
    {
      nixosModules = {
        rgbFusion = nixosModule;
        default   = nixosModule;
      };
    };
}
