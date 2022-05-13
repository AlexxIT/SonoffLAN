def save_to(store: list):
    return lambda *args, **kwargs: store.append({
        **dict(enumerate(args)), **kwargs
    })
