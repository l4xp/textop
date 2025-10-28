class classproperty(property):
    """
    A decorator that combines @classmethod and @property.
    Allows a method to be accessed as a property of the class.
    """
    def __get__(self, cls, owner):
        return self.fget.__get__(None, owner)()
