class ErrorMessage:
    err: any

    def __init__(self, err: any):
        self.err = err
        pass

    def get(self)->str:
        return repr(self.err)