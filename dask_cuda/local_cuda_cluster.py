import os

from tornado import gen

from dask.distributed import LocalCluster
from distributed.worker import TOTAL_MEMORY

from .utils import get_n_gpus


def cuda_visible_devices(i, visible=None):
    """ Cycling values for CUDA_VISIBLE_DEVICES environment variable

    Examples
    --------
    >>> cuda_visible_devices(0, range(4))
    '0,1,2,3'
    >>> cuda_visible_devices(3, range(8))
    '3,4,5,6,7,0,1,2'
    """
    if visible is None:
        try:
            visible = list(map(int, os.environ["CUDA_VISIBLE_DEVICES"].split(",")))
        except KeyError:
            visible = list(range(get_n_gpus()))

    L = visible[i:] + visible[:i]
    return ",".join(map(str, L))


class LocalCUDACluster(LocalCluster):
    def __init__(
        self,
        n_workers=None,
        threads_per_worker=1,
        processes=True,
        memory_limit=None,
        **kwargs,
    ):
        if n_workers is None:
            n_workers = get_n_gpus()
        if not processes:
            raise NotImplementedError("Need processes to segment GPUs")
        if n_workers > get_n_gpus():
            raise ValueError("Can not specify more processes than GPUs")
        if memory_limit is None:
            memory_limit = TOTAL_MEMORY / n_workers
        LocalCluster.__init__(
            self,
            n_workers=n_workers,
            threads_per_worker=threads_per_worker,
            memory_limit=memory_limit,
            **kwargs,
        )

    @gen.coroutine
    def _start(self, ip=None, n_workers=0):
        """
        Start all cluster services.
        """
        if self.status == "running":
            return
        if (ip is None) and (not self.scheduler_port) and (not self.processes):
            # Use inproc transport for optimization
            scheduler_address = "inproc://"
        elif ip is not None and ip.startswith("tls://"):
            scheduler_address = "%s:%d" % (ip, self.scheduler_port)
        else:
            if ip is None:
                ip = "127.0.0.1"
            scheduler_address = (ip, self.scheduler_port)
        self.scheduler.start(scheduler_address)

        yield [
            self._start_worker(
                **self.worker_kwargs,
                env={"CUDA_VISIBLE_DEVICES": cuda_visible_devices(i)},
            )
            for i in range(n_workers)
        ]

        self.status = "running"

        raise gen.Return(self)
