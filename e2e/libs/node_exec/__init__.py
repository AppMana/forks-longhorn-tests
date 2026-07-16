__all__ = ["NodeExec"]


def __getattr__(name):
    if name == "NodeExec":
        from node_exec.node_exec import NodeExec

        return NodeExec
    raise AttributeError(name)
