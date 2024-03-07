import pycrofluidics.common as common
import pathlib
import platformdirs
import ruamel.yaml as yaml

def main():
    """
    Generate config file, and fill with preset values. User will need to adapt it manually!
    """
    basepath = common.where_is_the_config_dir()
    configfile = common.where_is_the_config_file()
    yo = yaml.YAML()
    yo.dump(
        {
            'elveflow_dll': "/path/to/the/elveflow/dll",
            'elveflow_sdk': "/path/to/the/elveflow/sdk",
            'ob1_name' : "ASRL3::INSTR",
            'mux_name' : "ASRL4::INSTR",
            'ob1_callibration' : (basepath / "ob1_pressurechannel.callibration").as_posix(),
        },
        configfile
    )
    print(f"Configuration file was placed in:\n\t{configfile}\nPlease adapt it manually!")

if __name__ == "__main__":
    main()

