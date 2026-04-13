import json
import pandas as pd
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Constants for Fluxo mapping matching user request exactly
FLUXO_MAPPING = {
    '1.10 VAR ADESÃO': {'type': 'Adesão', 'value': 235},
    '1.75 MONITORAMENTO CCRI': {'type': 'Reparo', 'value': 80},
    '3.10 TEC CHAMADO TECNICO': {'type': 'Reparo', 'value': 80},
    '10.10 PME CHAMADO TECNICO': {'type': 'Reparo', 'value': 80},
    '1.50 VAR MUDANÇA DE ENDEREÇO': {'type': 'ME', 'value': 235},
    '3.50 TEC TROCA DE EQPT': {'type': 'Serviço', 'value': 40},
    '1.25 RECOLHE EQUIPO CANCELAM': {'type': 'Cancelamento', 'value': 40},
    '1.80 VAR TRANSFER INTERNA': {'type': 'Serviço', 'value': 80},
    '1.91 ALTERAÇÃO DE PLANO': {'type': 'Serviço', 'value': 80},
}

def map_fluxo(fluxo_val):
    if pd.isna(fluxo_val):
        return {'type': 'Outros', 'value': 0}
    # Check if any mapping key is in the string (in case there are extra spaces)
    for key, data in FLUXO_MAPPING.items():
        if key in str(fluxo_val):
            return data
    return {'type': 'Outros', 'value': 0}

def index(request):
    return render(request, 'dashboard/index.html')

@csrf_exempt
def process_data(request):
    if request.method == 'POST':
        acerta_file = request.FILES.get('acerta_file')
        loga_file = request.FILES.get('loga_file')

        if not acerta_file or not loga_file:
            return JsonResponse({'error': 'Please provide both Acerta and Loga files.'}, status=400)

        try:
            # Load DataFrames
            df_acerta = pd.read_excel(acerta_file)
            df_loga = pd.read_excel(loga_file)
            
            # Merge
            df = pd.concat([df_acerta, df_loga], ignore_index=True)
            
            # Apply mapping to create 'Atividade_Tipo' and 'Valor' columns
            mapped_data = df['Fluxo'].apply(map_fluxo)
            df['Atividade_Tipo'] = mapped_data.apply(lambda x: x['type'])
            df['Valor'] = mapped_data.apply(lambda x: x['value'])

            # Normalize columns
            user_col = next((col for col in df.columns if 'Usu' in col and 'Grupo' not in col), 'Usuário')
            status_col = next((col for col in df.columns if 'O.S.' in col and 'Situa' in col), 'Situação O.S.')
            cidade_col = 'Cidade' if 'Cidade' in df.columns else df.columns[4]
            date_col = next((col for col in df.columns if 'Data' in col), None)

            # Keep only technicians whose username ends with .dmais
            df = df[df[user_col].astype(str).str.strip().str.lower().str.endswith('.dmais', na=False)]

            # Metrics
            total_orders = len(df)
            total_revenue = df['Valor'].sum()
            
            # Completed revenue
            if status_col in df.columns:
                df_completed = df[df[status_col].astype(str).str.contains('Conclu', na=False, case=False)]
                completed_revenue = df_completed['Valor'].sum()
                completed_orders = len(df_completed)
            else:
                completed_revenue = 0
                completed_orders = 0
                
            pending_revenue = total_revenue - completed_revenue
            pending_orders = total_orders - completed_orders

            # Projeção: simple projection formula
            projection = float(total_revenue * 1.15) 
            
            active_techs = df[user_col].nunique() if user_col in df.columns else 0

            # Distribution by Technician (Top 6)
            tech_dist = df.groupby(user_col).agg(Valor=('Valor', 'sum'), Volume=('Valor', 'size')).reset_index().sort_values('Valor', ascending=False)
            top_techs = tech_dist.head(6)
            
            # Distribution by City (Top 6)
            city_dist = df.groupby(cidade_col).agg(Valor=('Valor', 'sum'), Volume=('Valor', 'size')).reset_index().sort_values('Valor', ascending=False)
            top_cities = city_dist.head(6)

            # Activity Types Pie
            activity_dist = df.groupby('Atividade_Tipo').size().reset_index(name='count').sort_values('count', ascending=False)
            
            if status_col in df.columns:
                df_pending = df.drop(df_completed.index)
                activity_dist_conc = df_completed.groupby('Atividade_Tipo').size().reset_index(name='count').sort_values('count', ascending=False)
                activity_dist_pend = df_pending.groupby('Atividade_Tipo').size().reset_index(name='count').sort_values('count', ascending=False)
            else:
                activity_dist_conc = activity_dist
                activity_dist_pend = activity_dist
            
            # Timeline (Revenue by hour -> assume 06h to 18h)
            timeline_data = []
            if date_col and df[date_col].dtype != 'O': # check if datetime
                df['Hora'] = pd.to_datetime(df[date_col], errors='coerce').dt.hour
                hourly = df.groupby('Hora')['Valor'].sum().reset_index()
                # Ensure 06h to current (or 18h)
                for h in range(6, 19):
                    val = float(hourly.loc[hourly['Hora'] == h, 'Valor'].sum()) if h in hourly['Hora'].values else 0.0
                    timeline_data.append({'hour': f"{h:02d}h", 'valor': val})

            # Fila de atendimento (Top 10 rows)
            # OS, Técnico, Cidade, Atividade, Valor
            fila_cols = []
            os_col = next((col for col in df.columns if 'ID O.S.' in col), df.columns[0])
            fila_df = df.head(10).fillna('')
            fila = []
            for _, row in fila_df.iterrows():
                fila.append({
                    'OS': str(row.get(os_col, 'N/A')),
                    'Técnico': str(row.get(user_col, 'N/A')),
                    'Cidade': str(row.get(cidade_col, 'N/A')),
                    'Atividade': str(row.get('Atividade_Tipo', 'N/A')),
                    'Valor': float(row.get('Valor', 0)),
                    'Situação': str(row.get(status_col, ''))
                })

            response_data = {
                'metrics': {
                    'total_orders': int(total_orders),
                    'completed_orders': int(completed_orders),
                    'pending_orders': int(pending_orders),
                    'total_revenue': float(total_revenue),
                    'completed_revenue': float(completed_revenue),
                    'pending_revenue': float(pending_revenue),
                    'projection': float(projection),
                    'active_techs': int(active_techs),
                },
                'tech_distribution': {
                    'labels': [str(x) for x in top_techs[user_col].tolist()],
                    'values': [float(x) for x in top_techs['Valor'].tolist()],
                    'volumes': [int(x) for x in top_techs['Volume'].tolist()]
                },
                'city_distribution': {
                    'labels': [str(x) for x in top_cities[cidade_col].tolist()],
                    'values': [float(x) for x in top_cities['Valor'].tolist()],
                    'volumes': [int(x) for x in top_cities['Volume'].tolist()]
                },
                'activity_distribution': {
                    'all': {
                        'labels': [str(x) for x in activity_dist['Atividade_Tipo'].tolist()],
                        'values': [int(x) for x in activity_dist['count'].tolist()]
                    },
                    'conc': {
                        'labels': [str(x) for x in activity_dist_conc['Atividade_Tipo'].tolist()],
                        'values': [int(x) for x in activity_dist_conc['count'].tolist()]
                    },
                    'pend': {
                        'labels': [str(x) for x in activity_dist_pend['Atividade_Tipo'].tolist()],
                        'values': [int(x) for x in activity_dist_pend['count'].tolist()]
                    }
                },
                'timeline': timeline_data,
                'fila': fila
            }

            return JsonResponse(response_data)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)
