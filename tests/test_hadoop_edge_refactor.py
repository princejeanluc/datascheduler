"""
DataScheduler — tests/test_hadoop_edge_refactor.py
Vérifie que le refactor core/spark.py → core/hadoop_edge.py (chantier K) est bien invisible pour
les appelants existants : chaque nom historiquement importé depuis core.spark reste importable
de là ET pointe vers exactement le même objet que core.hadoop_edge (pas une copie qui dérive).
"""

import core.hadoop_edge as hadoop_edge
import core.spark as spark


def test_reexported_names_are_the_same_objects():
    for name in (
        "SshExecConfig", "KerberosConfig", "ConnectionTestResult",
        "config_from_profile", "kerberos_config_from_profile",
        "test_ssh_connection", "test_kerberos_auth",
    ):
        assert getattr(spark, name) is getattr(hadoop_edge, name), name
