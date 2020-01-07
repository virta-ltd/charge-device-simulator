import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="charge-device-sim-virta",
    version="1.0.0",
    author="Virta Ltd",
    author_email="mostafa.aghajani@virta.global",
    description="Easy to use charge device simulators for different protocols like OCPP and Ensto",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/virta-ltd/charge-device-simulator",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Public v3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
