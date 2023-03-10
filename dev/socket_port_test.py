import importlib

pysweepme = importlib.import_module("pysweepme", r"C:\Users\Ivan Ramirez\Documents\pysweepme")
import pysweepme

waferproberpath = r"C:\Users\Ivan Ramirez\Documents\SweepMe!\Devices\WaferProber-MPI_SENTIO"
pysweepme.get_device("WaferProber-MPI_SENTIO", waferproberpath, "127.0.0.1:65432")