import logging

import glawit.core.access
import glawit.core.json64

logger = logging.getLogger(
    __name__,
)


def post(
            boto3_session,
            config,
            request,
            session,
            requests_session,
        ):
    viewer_access = session['GitHub']['viewer_access']

    if viewer_access >= glawit.core.access.RepositoryAccess.WRITE:
        locktable = config['locktable']

        data = request['data']

        dynamodb = boto3_session.client(
            'dynamodb',
        )

        scan_arguments_ours = {
        }
        scan_arguments_theirs = {
        }

        try:
            cursors_encoded = data['cursor']
        except KeyError:
            pass
        else:
            cursors = glawit.core.json64.decode(
                cursors_encoded,
            )

            try:
                cursor_ours = cursors['ours']
            except KeyError:
                pass
            else:
                scan_arguments_ours['ExclusiveStartKey'] = cursor_ours

            try:
                cursor_theirs = cursors['theirs']
            except KeyError:
                pass
            else:
                scan_arguments_theirs['ExclusiveStartKey'] = cursor_theirs

        try:
            limit_str = data['limit']
        except KeyError:
            limit = config['API']['pagination']['max']
        else:
            limit = min(
                max(
                    max(
                        config['API']['pagination']['min'],
                        2,
                    ),
                    int(
                        limit_str,
                    ),
                ),
                config['API']['pagination']['max'],
            )

        half_limit = limit // 2

        try:
            request_ref = data['ref']
        except KeyError:
            pass
        else:
            ref = request_ref['name']
            logger.debug(
                'git ref: %s',
                ref,
            )

        next_cursors = {
        }

        current_github_user_id = session['GitHub']['id']

        response = dynamodb.scan(
            **scan_arguments_ours,
            ExpressionAttributeValues={
                ':github_id': {
                    'S': current_github_user_id,
                },
            },
            FilterExpression='github_id = :github_id',
            Limit=half_limit,
            ReturnConsumedCapacity='NONE',
            Select='ALL_ATTRIBUTES',
            TableName=locktable,
        )

        items = response['Items']

        github_ids = [
            item['github_id']['S']
            for item in items
        ]

        github_users = glawit.core.github.fetch_users_info(
            authorization_header_value=session['GitHub']['authorization_header_value'],
            github_ids=github_ids,
            requests_session=requests_session,
        )

        ours = [
            {
                'id': item['path']['S'],
                'path': item['path']['S'],
                'locked_at': item['creation_time']['S'],
                'owner': {
                    'name': f'{ github_users[item["github_id"]["S"]]["login"] } ({ github_users[item["github_id"]["S"]]["name"]})',
                },
            }
            for item in items
        ]

        try:
            last_evaluated_key = response['LastEvaluatedKey']
        except KeyError:
            logger.debug(
                'no more results',
            )
        else:
            next_cursors['ours'] = last_evaluated_key

        response = dynamodb.scan(
            **scan_arguments_theirs,
            ExpressionAttributeValues={
                ':github_id': {
                    'S': current_github_user_id,
                },
            },
            FilterExpression='github_id <> :github_id',
            Limit=half_limit,
            ReturnConsumedCapacity='NONE',
            Select='ALL_ATTRIBUTES',
            TableName=locktable,
        )

        items = response['Items']

        github_ids = [
            item['github_id']['S']
            for item in items
        ]

        github_users = glawit.core.github.fetch_users_info(
            authorization_header_value=session['GitHub']['authorization_header_value'],
            github_ids=github_ids,
            requests_session=requests_session,
        )

        theirs = [
            {
                'id': item['path']['S'],
                'path': item['path']['S'],
                'locked_at': item['creation_time']['S'],
                'owner': {
                    'name': f'{ github_users[item["github_id"]["S"]]["login"] } ({ github_users[item["github_id"]["S"]]["name"]})',
                },
            }
            for item in items
        ]

        try:
            last_evaluated_key = response['LastEvaluatedKey']
        except KeyError:
            logger.debug(
                'no more results',
            )
        else:
            next_cursors['theirs'] = last_evaluated_key

        status_code = 200
        response_data = {
            'ours': ours,
            'theirs': theirs,
        }

        if next_cursors:
            response_data['next_cursor'] = glawit.core.json64.encode(
                next_cursors,
            )
    else:
        status_code = 403
        response_data = {
            'message': 'You are not allowed to push to this repository',
        }

    response = {
        'body': response_data,
        'headers': {
            'Content-Type': 'application/vnd.git-lfs+json',
        },
        'statusCode': status_code,
    }

    return response
