#!/bin/sh
echo "tag_sb: $BUILD_SOURCEBRANCH"
echo "tag_tb: $SYSTEM_PULLREQUEST_TARGETBRANCH"
# - export TAG=`if [ "$BUILD_SOURCEBRANCH" == "develop" ]; then echo "latest"; else echo $BUILD_SOURCEBRANCH ; fi`
# Replace / with _ to create a valid tag
if [ -z ${SYSTEM_PULLREQUEST_TARGETBRANCH} ]; then
    TAG=$(echo "${BUILD_SOURCEBRANCH}" | sed -e "s/\//_/g")
else
    TAG=$(echo "${SYSTEM_PULLREQUEST_TARGETBRANCH}" | sed -e "s/\//_/g")
fi

TAG_PI="${TAG}_pi"

echo "tag: $TAG"

# Add commit and commit_message to docker container
echo "${BUILD_SOURCEVERSION} ${BUILD_SOURCEVERSIONMESSAGE}" > freqtrade_commit

if [ "${BUILD_REASON}" = "cron" ]; then
    echo "event ${BUILD_REASON}: full rebuild - skipping cache"
    docker build -t freqtrade:${TAG} .

    echo "event ${TRAVIS_EVENT_TYPE}: full rebuild - skipping cache"
    docker build -f Dockerfile.pi -t freqtrade:${TAG_PI} .
else
    echo "event ${BUILD_REASON}: building with cache"
    # Pull last build to avoid rebuilding the whole image
    docker pull ${IMAGE_NAME}:${TAG}
    docker build --cache-from ${IMAGE_NAME}:${TAG} -t freqtrade:${TAG} .

    # docker pull ${IMAGE_NAME}:${TAG_PI}
    docker build -f Dockerfile.pi -t freqtrade:${TAG_PI} .
    # docker build --cache_from ${IMAGE_NAME}:${TAG_PI} -f Dockerfile.pi -t freqtrade:${TAG_PI} .
fi

if [ $? -ne 0 ]; then
    echo "failed building image"
    return 1
fi

# Run backtest
docker run --rm -v $(pwd)/config.json.example:/freqtrade/config.json:ro freqtrade:${TAG} --datadir freqtrade/tests/testdata backtesting

if [ $? -ne 0 ]; then
    echo "failed running backtest"
    return 1
fi

# Tag image for upload
docker tag freqtrade:$TAG ${IMAGE_NAME}:$TAG
if [ $? -ne 0 ]; then
    echo "failed tagging image"
    return 1
fi

# Tag as latest for develop builds
if [ "${BUILD_SOURCEBRANCH}" = "develop" ]; then
    docker tag freqtrade:$TAG ${IMAGE_NAME}:latest
fi

# Login
# Don't push for now (wedon't have docker configued for pipelines yet)
# echo "$DOCKER_PASS" | docker login -u $DOCKER_USER --password-stdin

# if [ $? -ne 0 ]; then
#     echo "failed login"
#     return 1
# fi

# Show all available images
docker images


# exit 0
# docker push ${IMAGE_NAME}
# if [ $? -ne 0 ]; then
#     echo "failed pushing repo"
#     return 1
# fi
