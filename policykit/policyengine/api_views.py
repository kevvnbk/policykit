from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from django.contrib.auth import get_user
from django.db import transaction
from silk.profiling.profiler import silk_profile
from policyengine.serializers import MembersSerializer, PutMembersRequestSerializer, CommunityDashboardSerializer, LogsSerializer

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def members(request):
    user = get_user(request)

    if request.method == 'GET':
        return Response(MembersSerializer(user.community.community).data)


    if request.method == 'PUT':
        req = PutMembersRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        put_members(user, **req.validated_data)
        return Response({}, status=200)

    raise NotImplementedError

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@silk_profile()
def dashboard(request):
    user = get_user(request)
    return Response(CommunityDashboardSerializer(user.community.community).data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def logs(request):
    user = get_user(request)
    return Response(LogsSerializer(user.community.community).data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def settings(request):
    from policyengine.views import integration_data
    from policyengine.metagov_app import metagov
    from django.conf import settings as django_settings
    import logging

    logger = logging.getLogger(__name__)
    user = get_user(request)
    community = user.community
    INTEGRATION_ADMIN_ROLE_NAME = "Integration Admin"

    enabled_integrations = []
    disabled_integrations = []

    if community.metagov_slug:
        enabled_dict = {}
        # Iterate through all Metagov Plugins enabled for this community
        for plugin in metagov.get_community(community.metagov_slug).plugins.all():
            integration = plugin.name
            if integration not in integration_data.keys():
                logger.warn(f"unsupported integration {integration} is enabled for community {community}")
                continue

            # Only include configs if user has permission, since they may contain API Keys
            config_tuples = []
            if user.has_role(INTEGRATION_ADMIN_ROLE_NAME):
                for (k,v) in plugin.config.items():
                    readable_key = k.replace("_", " ").replace("-", " ").capitalize()
                    config_tuples.append([readable_key, v])

            # Add additional data about the integration, like description and webhook URL
            additional_data = integration_data[integration]
            if additional_data.get("webhook_instructions"):
                additional_data["webhook_url"] = f"{django_settings.SERVER_URL}/api/hooks/{plugin.name}/{plugin.community.slug}"

            enabled_dict[integration] = {**plugin.serialize(), **additional_data, "config": config_tuples}

        enabled_integrations = list(enabled_dict.items())
        disabled_integrations = [[k, v] for (k,v) in integration_data.items() if k not in enabled_dict.keys()]

    return Response({
        "enabled_integrations": enabled_integrations,
        "disabled_integrations": disabled_integrations
    })

@api_view(['PUT', 'POST'])
@permission_classes([IsAuthenticated])
def community_doc(request):
    user = get_user(request)
    community = user.community.community
    doc_id = request.data.get('id')
    text = request.data.get('text')
    name = request.data.get('name')

    if doc_id is not None:
        try:
            doc = community.get_documents().get(id=doc_id)
        except community.get_documents().model.DoesNotExist:
            raise NotFound('Document not found')
    else:
        # Create a new document if no ID is provided
        from policyengine.models import CommunityDoc
        doc = CommunityDoc(community=community)

    if text is not None:
        doc.text = text
    if name is not None:
        doc.name = name

    doc.save()
    return Response({}, status=200)



def put_members(user, action, role, members):
    from constitution.models import (PolicykitAddUserRole,
                                     PolicykitRemoveUserRole)

    from policyengine.models import CommunityRole, CommunityUser

    action_model = None
    if action == 'Add':
        action_model = PolicykitAddUserRole()
    elif action == 'Remove':
        action_model = PolicykitRemoveUserRole()
    else:
        raise ValueError('Invalid action')

    action_model.community = user.constitution_community
    action_model.initiator = user
    try:
        action_model.role = CommunityRole.objects.filter(pk=role, community=user.community.community)[0]
    except IndexError:
        raise NotFound('Role not found')

    action_model.save(evaluate_action=False)
    action_model.users.set(CommunityUser.objects.filter(id__in=members, community__community=user.community.community))
    if len(action_model.users.all()) != len(members):
        raise NotFound('User not found')
    action_model.save(evaluate_action=True)


@api_view(['POST'])
@permission_classes([AllowAny])
def deploy_generated_policy(request):
    """
    Create a GeneratedPolicy from a script produced by an external policy
    generation pipeline (see policy-llm's /deploy_to_policykit).

    Prototype-grade auth: a single shared secret (X-Deploy-Secret header,
    checked against POLICYKIT_DEPLOY_SECRET) and a single hardcoded target
    community (POLICYKIT_DEPLOY_COMMUNITY_ID) -- not how this would work for
    real multi-tenant use. See NOTES.md.
    """
    from django.conf import settings
    from policyengine.models import Community, GeneratedPolicy, ActionType
    from policyengine.script_adapter import (
        execute_generated_script,
        RegistrationOnlyContext,
        event_type_to_action_type_codename,
    )

    if not settings.POLICYKIT_DEPLOY_SECRET:
        return Response({"error": "POLICYKIT_DEPLOY_SECRET is not configured on this server"}, status=500)

    provided_secret = request.headers.get("X-Deploy-Secret")
    if provided_secret != settings.POLICYKIT_DEPLOY_SECRET:
        return Response({"error": "invalid or missing X-Deploy-Secret header"}, status=403)

    name = request.data.get("name")
    script_code = request.data.get("script_code")
    if not name or not script_code:
        return Response({"error": "both 'name' and 'script_code' are required"}, status=400)

    if not settings.POLICYKIT_DEPLOY_COMMUNITY_ID:
        return Response({"error": "POLICYKIT_DEPLOY_COMMUNITY_ID is not configured on this server"}, status=500)
    try:
        community = Community.objects.get(pk=settings.POLICYKIT_DEPLOY_COMMUNITY_ID)
    except Community.DoesNotExist:
        return Response(
            {"error": f"configured POLICYKIT_DEPLOY_COMMUNITY_ID={settings.POLICYKIT_DEPLOY_COMMUNITY_ID} does not exist"},
            status=500,
        )

    # Validate the script and derive which ActionTypes it needs, in one dry
    # run of setup(ctx) -- see RegistrationOnlyContext's docstring for why
    # this is safe to do before any real Proposal/Action exists. A script
    # that can't even run its own setup() has no business being saved as an
    # active policy.
    reg_ctx = RegistrationOnlyContext()
    try:
        execute_generated_script(script_code, "setup", ctx=reg_ctx)
    except Exception as e:
        return Response({"error": f"script failed validation: {type(e).__name__}: {e}"}, status=400)

    action_type_codenames = set()
    unmapped_event_types = []
    for event_type in reg_ctx.event_types:
        codename = event_type_to_action_type_codename(event_type)
        if codename:
            action_type_codenames.add(codename)
        else:
            unmapped_event_types.append(event_type)

    if not action_type_codenames:
        return Response({
            "error": "script's setup(ctx) didn't register any handlers whose event type maps to a known ActionType",
            "registered_event_types": reg_ctx.event_types,
        }, status=400)

    policy = GeneratedPolicy.objects.create(
        kind='platform', name=name, community=community, script_code=script_code,
    )
    for codename in action_type_codenames:
        action_type, _ = ActionType.objects.get_or_create(codename=codename)
        policy.action_types.add(action_type)

    return Response({
        "success": True,
        "policy_id": policy.pk,
        "action_types": sorted(action_type_codenames),
        "unmapped_event_types": unmapped_event_types,
    }, status=201)

