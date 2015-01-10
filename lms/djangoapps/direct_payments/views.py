"""
View endpoints for direct payments
"""
from datetime import datetime
import pytz
from django.conf import settings
from django.contrib.auth.models import Group
from django.http import (
    HttpResponse, HttpResponseRedirect, HttpResponseNotFound,
    HttpResponseBadRequest, HttpResponseForbidden, Http404
)
from util.json_request import JsonResponse, expect_json
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from django.core.exceptions import ObjectDoesNotExist
from edxmako.shortcuts import render_to_response
from shoppingcart.models import Order, OrderItem

from .models import Charge, UserBalance

@login_required
def index(request):
    """
    This view shows direct_payments_form
    """
    charges = Charge.objects.filter(user=request.user)
    context = {
        'charges':charges
    }
    return render_to_response("direct_payments/index.html", context)

def testing_view(request):
    """
    for testing
    """
    charges = Charge.objects.filter(user=request.user)
    context = {
        'charges':charges
    }
    return render_to_response("testing_page.html", context)


@login_required
def new_charge(request):
    """
    create new charge with amount and attachment image and user notes
    """
    if request.method == 'POST':
        attachment = request.FILES.get('attachment', None)
        if attachment:
            c = Charge(user=request.user,
                   amount=request.POST.get('amount', 0),
                   user_notes=request.POST.get('user_notes', "NoNo"),
                   attachment=request.FILES['attachment'])
            c.save()
            return redirect('dashboard')
        
        return JsonResponse({'msg':'No files attached'}, status=400)
    
    return JsonResponse({'msg':'Bad Request'}, status=400)
  
    
@login_required
def remove_charge_entry(request):
    """
    this will mark the charge entry as "is_shown=False" and won't actually remove it
    """
    if request.method == 'POST':
        charge_id = int(request.POST['charge']) if request.POST.get('charge', None) else None
        if charge_id:
            try:
                c = Charge.objects.get(pk=charge_id)
                if c.user == request.user or request.user.is_superuser:
                    c.hide()
                    return JsonResponse({'msg':'Removed'}, status=200)
            except ObjectDoesNotExist:
                return JsonResponse({'msg':'Charge not found'}, status=404)
        else:
            return JsonResponse({'msg':'Missig paramaters'}, status=400)
    
    return JsonResponse({'msg':'Bad Request'}, status=400)


@login_required
def update_charge_amount(request):
    """
    update the initial charge amount
    """
    if request.method == 'POST':
        charge_id = int(request.POST['charge']) if request.POST.get('charge', None) else None
        new_amount = int(request.POST['new_amount']) if request.POST.get('new_amount', None) else None
        if charge_id & new_amount:
            try:
                c = Charge.objects.get(pk=charge_id)
                if c.user == request.user or request.user.is_superuser:
                    c.amount = new_amount
                    c.save()
                    return JsonResponse({'msg':'Updated'}, status=200)
            except ObjectDoesNotExist:
                return JsonResponse({'msg':'Charge not found'}, status=404)
        else:
            return JsonResponse({'msg':'Missig paramaters'}, status=400)
        
    return JsonResponse({'msg':'Bad Request'}, status=400)


@login_required
def update_charge_status(request):
    """
    update charge status
    """
    if request.method == 'POST':
        charge_id = int(request.POST['charge']) if request.POST.get('charge', None) else None
        status = request.POST.get('status', None)
        if charge_id and status:
            try:
                c = Charge.objects.get(pk=charge_id)
                if status not in ['pending', 'rejected', 'canceled', 'approved']:
                    return JsonResponse({'msg':'Not supported'}, status=400)
                if c.user == request.user or request.user.is_superuser:
                    c.update_status(status, request)
                    return JsonResponse({'msg':'Updated'}, status=200)
            except ObjectDoesNotExist:
                return JsonResponse({'msg':'Charge not found'}, status=404)
        else:
            return JsonResponse({'msg':'Missig paramaters'}, status=400)
        
    return JsonResponse({'msg':'Bad Request'}, status=400)


@login_required
def add_charge_comment(request):
    """
    add comment to charge entry
    """
    if request.method == 'POST':
        charge_id = int(request.POST['charge']) if request.POST.get('charge', None) else None
        content = request.POST.get('content', None)
        if charge_id and content:
            try:
                c = Charge.objects.get(pk=charge_id)
                if len(content) < 1:
                    return JsonResponse({'msg':'provide comment'}, status=400)
                if c.user == request.user or request.user.is_superuser:
                    c.add_comment(content, request)
                    return JsonResponse({'msg':'Comment added'}, status=200)
            except ObjectDoesNotExist:
                return JsonResponse({'msg':'Charge not found'}, status=404)
        else:
            return JsonResponse({'msg':'Missig paramaters'}, status=400)
        
    return JsonResponse({'msg':'Bad Request'}, status=400)

@require_POST
@login_required
def direct_purchase_order(request):
    """
    complete payment order
    """
    order_id = request.POST.get('reference_number', None)
    try:
        order = Order.objects.get(id=order_id)

    except DoesNotExist:
        return JsonResponse({'msg':'Wrong order'}, status=404)
    
    balance = UserBalance.get_user_balance(request.user)
    order_total_cost = order.total_cost
    
    if balance.current_balance == 0:
        order.put_on_hold()
        # redirect to add charges page
        return JsonResponse({'msg':'No balance, all onhold'}, status=200)
    elif balance.current_balance >= order_total_cost:
        order.purchase()
        balance.deduct_amount(order_total_cost)
        
        # redirect to show receipt
        return redirect(reverse('shoppingcart.views.show_receipt', args=[order.id]))
    else:
        items = OrderItem.objects.filter(order=order).select_subclasses('onholdpaidregistration')
        for item in items:
            if not item.status == 'purchased':
                if balance.current_balance >= item.line_cost:
                    item.purchase_item()
                    balance.deduct_amount(item.line_cost)
                else:
                    item.put_on_hold()
                    
        if OrderItem.objects.filter(order=order, status='onhold').select_subclasses('onholdpaidregistration').exists():
            order.status = 'onhold'
            order.save()
            # TODO: redirect to some descriptive message
            return JsonResponse({'msg':'Order still has onhold registration/s'}, status=200)
        else:
            order.status = 'purchased'
            order.purchase_time = datetime.now(pytz.utc)
            order.save()
            return JsonResponse({'msg':'Order purchased'}, status=200)
        
        return redirect(reverse('dashboard'))                                           
    
    return JsonResponse({'msg':'Bad Request'}, status=400)
