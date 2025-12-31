import traceback
import sys


class ErrorMessage:
    err: any

    def __init__(self, err: any):
        self.err = err
        pass

    def get(self) -> any:
        # log_traceback = []
        # try:
        #     exc_type, exc_value, exc_traceback = sys.exc_info()
        #     log_traceback = traceback.format_exception(exc_type, exc_value, exc_traceback)
        # except:
        #     pass
        return {
            "message": f"{repr(self.err)}",
            "error_type": type(self.err),
            # "trace_back": log_traceback,
        }
